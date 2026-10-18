import sys
import json
import math
from pathlib import Path

try:
    import bpy
    from mathutils import Vector, Euler
except ImportError:
    bpy = None
    Vector = None
    Euler = None

def get_cli_arguments() -> dict:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parsed = {}
    for i in range(0, len(argv), 2):
        if i + 1 < len(argv):
            parsed[argv[i].lstrip("-")] = argv[i + 1]
    return parsed

def enforce_4gb_vram_discipline(scene_cfg: dict, max_tex_res: int = 2048):
    """
    THÔNG SỐ 5 - Kỷ luật bộ nhớ 4GB VRAM trên Quadro P2000:
    1. Dọn sạch dữ liệu mồ côi (Orphan meshes/materials/textures).
    2. Hạ độ phân giải mọi Texture vượt quá 2K (2048x2048) ngay trong RAM trước khi đẩy lên VRAM.
    3. Tạo các vật thể lặp lại (cây cối, bàn ghế) bằng kỹ thuật Instancing (link=True).
    """
    if bpy is None:
        return

    try:
        bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
    except Exception:
        pass

    for img in bpy.data.images:
        if img.size[0] > max_tex_res or img.size[1] > max_tex_res:
            new_w = min(img.size[0], max_tex_res)
            new_h = min(img.size[1], max_tex_res)
            img.scale(new_w, new_h)

    if hasattr(bpy.context.preferences.system, "gl_texture_limit"):
        bpy.context.preferences.system.gl_texture_limit = 'CLAMP_2048'

    # Thực thi Instancing (link=True) cho các đồ vật lặp lại trong bối cảnh
    for prop_group in scene_cfg.get("instanced_props", []):
        src_name = prop_group.get("source_object_name")
        src_obj = bpy.data.objects.get(src_name)
        if not src_obj:
            continue
        for idx, loc in enumerate(prop_group.get("instance_locations", [])):
            inst_name = f"{src_name}_Instance_{idx:02d}"
            if inst_name not in bpy.data.objects:
                inst_obj = src_obj.copy()
                inst_obj.data = src_obj.data  # link=True: chia sẻ 100% Mesh & UV trong VRAM
                inst_obj.name = inst_name
                bpy.context.collection.objects.link(inst_obj)
            bpy.data.objects[inst_name].location = Vector(loc)

def setup_eevee_cinematic_pipeline(scene, meta: dict, scene_cfg: dict):
    """
    Thiết lập THÔNG SỐ 2 (Volumetrics & Soft Shadows), THÔNG SỐ 3 (SSR & GTAO),
    và THÔNG SỐ 4 (Quản lý màu sắc chuẩn rạp AgX - High Contrast).
    """
    if bpy is None:
        return

    engines = [e.identifier for e in scene.render.bl_rna.properties['engine'].enum_items]
    scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engines else 'BLENDER_EEVEE'
    eevee = scene.eevee

    # THÔNG SỐ 2: Ánh sáng thể tích (Volumetrics) & Bóng đổ mềm (Soft Shadows)
    if hasattr(eevee, "use_volumetric_lighting"):
        eevee.use_volumetric_lighting = bool(scene_cfg.get("volumetric_lighting", True))
        eevee.use_volumetric_shadows = True
        eevee.volumetric_tile_size = '8'
    if hasattr(eevee, "use_soft_shadows"):
        eevee.use_soft_shadows = True
        eevee.shadow_cube_size = '1024'
        eevee.shadow_cascade_size = '2048'

    # Tạo sương/bụi thể tích nhẹ trong World Shader nếu chưa có
    if scene.world and scene.world.use_nodes:
        tree = scene.world.node_tree
        if "Volume Scatter" not in [n.bl_idname for n in tree.nodes]:
            vol_node = tree.nodes.new(type="ShaderNodeVolumeScatter")
            vol_node.inputs["Density"].default_value = float(scene_cfg.get("volumetric_density", 0.025))
            vol_node.inputs["Anisotropy"].default_value = 0.6
            out_node = next((n for n in tree.nodes if n.bl_idname == "ShaderNodeOutputWorld"), None)
            if out_node:
                tree.links.new(vol_node.outputs["Volume"], out_node.inputs["Volume"])

    # THÔNG SỐ 3: Phản chiếu không gian màn hình (SSR) & Chiều sâu góc khuất (GTAO)
    if hasattr(eevee, "use_ssr"):
        eevee.use_ssr = True
        eevee.use_ssr_refraction = True
        eevee.ssr_quality = 0.55
    if hasattr(eevee, "use_gtao"):
        eevee.use_gtao = True
        eevee.gtao_distance = 0.45

    eevee.taa_render_samples = 32

    # THÔNG SỐ 4: Quản lý màu sắc chuẩn rạp AgX - High Contrast
    cm = scene.view_settings
    target_transform = meta["color_management"].get("view_transform", "AgX")
    target_look = meta["color_management"].get("look", "AgX - High Contrast")
    try:
        cm.view_transform = target_transform
        cm.look = target_look
    except TypeError:
        cm.view_transform = "Filmic"
        cm.look = "High Contrast"

def setup_three_point_lighting(speaker_pos, camera_pos):
    """
    THÔNG SỐ 2 (Tiếp): Thiết lập hệ thống đèn 3-Point Lighting chuẩn điện ảnh:
    - Key Light (Ấm 3200K): Tạo khối sáng chính trên gương mặt.
    - Fill Light (Dịu 5600K): Cân bằng vùng tối bên má khuất sáng.
    - Rim Light (Đèn tách tóc): Đánh ngược từ phía sau lưng để tách viền nhân vật khỏi phông nền.
    """
    if bpy is None:
        return

    for ob in list(bpy.data.objects):
        if ob.name.startswith("CINE_3PT_"):
            bpy.data.objects.remove(ob, do_unlink=True)

    head_target = speaker_pos + Vector((0.0, 0.0, 1.62))
    cam_dir = (camera_pos - head_target).normalized()
    side_vec = cam_dir.cross(Vector((0.0, 0.0, 1.0))).normalized()

    rig_specs = [
        ("CINE_3PT_KEY",  head_target + cam_dir * 1.45 + side_vec * 1.15 + Vector((0, 0, 0.65)), 135.0, (1.00, 0.87, 0.74), 1.1),
        ("CINE_3PT_FILL", head_target + cam_dir * 1.65 - side_vec * 1.35 + Vector((0, 0, 0.25)),  45.0, (0.80, 0.89, 1.00), 1.7),
        ("CINE_3PT_RIM",  head_target - cam_dir * 1.25 - side_vec * 0.35 + Vector((0, 0, 0.75)), 105.0, (0.96, 0.98, 1.00), 0.65),
    ]

    for light_name, loc, power, color_rgb, area_size in rig_specs:
        l_data = bpy.data.lights.new(name=light_name, type='AREA')
        l_data.energy = power
        l_data.color = color_rgb
        l_data.size = area_size
        if hasattr(l_data, "use_contact_shadow"):
            l_data.use_contact_shadow = True
        l_obj = bpy.data.objects.new(name=light_name, object_data=l_data)
        bpy.context.collection.objects.link(l_obj)
        l_obj.location = loc
        l_obj.rotation_euler = (head_target - loc).to_track_quat('-Z', 'Y').to_euler()

def get_eye_bone_world_location(char_id: str, char_cfg: dict, actor_state: dict):
    """Lấy tọa độ thế giới chính xác của xương mắt (`eye_bone_name`) trên nhân vật."""
    if bpy is None:
        return None

    arm_name = char_cfg.get("armature_name", char_id)
    eye_bone_name = char_cfg.get("eye_bone_name", "Bone_Eye_Target")
    arm_obj = bpy.data.objects.get(arm_name) or bpy.data.objects.get(char_id)

    if arm_obj and arm_obj.type == 'ARMATURE' and eye_bone_name in arm_obj.pose.bones:
        pose_bone = arm_obj.pose.bones[eye_bone_name]
        return arm_obj.matrix_world @ pose_bone.head

    base_pos = Vector(actor_state["position_xyz"])
    height_m = float(char_cfg.get("height_m", 1.72))
    return base_pos + Vector((0.0, 0.0, height_m * 0.91))

def setup_camera_dof_and_rack_focus(scene, shot: dict, characters_cfg: dict, fps: int):
    """
    THÔNG SỐ 1: Ống kính 50mm-85mm, Xóa phông vật lý (f/2.0) khóa vào xương mắt nhân vật
    và tự động trượt điểm lấy nét (Rack Focus) khi chuyển lượt nói.
    """
    if bpy is None:
        return

    cam_cfg = shot["camera"]
    cam_data = bpy.data.cameras.new("CINE_SHOT_CAM_DATA")
    cam_data.lens = max(50.0, min(85.0, float(cam_cfg.get("lens_mm", 85.0))))
    cam_data.sensor_width = 36.0

    cam_data.dof.use_dof = True
    cam_data.dof.aperture_fstop = float(cam_cfg.get("aperture_fstop", 2.0))

    cam_obj = bpy.data.objects.new("CINE_SHOT_CAMERA", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    scene.camera = cam_obj

    cam_obj.location = Vector(cam_cfg["location_xyz"])
    cam_obj.rotation_euler = Euler([math.radians(d) for d in cam_cfg["rotation_euler_deg"]], 'XYZ')

    focus_target = bpy.data.objects.new("CINE_EYE_FOCUS_TARGET", None)
    bpy.context.collection.objects.link(focus_target)
    cam_data.dof.focus_object = focus_target

    spk_id = shot["speaker"]
    spk_eye_loc = get_eye_bone_world_location(spk_id, characters_cfg.get(spk_id, {}), shot["actors"][spk_id])

    rack_cfg = shot.get("rack_focus", {})
    if rack_cfg.get("enabled") and rack_cfg.get("from_character") in shot["actors"]:
        from_id = rack_cfg["from_character"]
        to_id = rack_cfg["to_character"]
        from_loc = get_eye_bone_world_location(from_id, characters_cfg.get(from_id, {}), shot["actors"][from_id])
        to_loc = get_eye_bone_world_location(to_id, characters_cfg.get(to_id, {}), shot["actors"][to_id])

        f_start = max(1, int(round(float(rack_cfg.get("start_sec", 0.2)) * fps)))
        f_end = max(f_start + 1, int(round(float(rack_cfg.get("end_sec", 0.8)) * fps)))

        focus_target.location = from_loc
        focus_target.keyframe_insert(data_path="location", frame=1)
        focus_target.keyframe_insert(data_path="location", frame=f_start)

        focus_target.location = to_loc
        focus_target.keyframe_insert(data_path="location", frame=f_end)
    else:
        focus_target.location = spk_eye_loc

def apply_mixamo_and_lipsync_keyframes(
    char_id: str,
    char_cfg: dict,
    actor_state: dict,
    viseme_json_path: Path,
    is_speaker: bool
):
    """
    Đặt nhân vật vào đúng tọa độ, nạp chuyển động Mixamo (.fbx) và đóng Keyframe
    khẩu hình (A, O, E, M, F) điều khiển trực tiếp môi (Shape Keys) và xương hàm (Jaw Bone).
    """
    if bpy is None:
        return

    arm_name = char_cfg.get("armature_name", char_id)
    char_obj = bpy.data.objects.get(arm_name) or bpy.data.objects.get(char_id)

    # Nếu nhân vật chưa có sẵn trong file .blend thì nạp từ file .fbx
    if not char_obj:
        fbx_file = Path(char_cfg.get("fbx_path", ""))
        if fbx_file.exists():
            bpy.ops.import_scene.fbx(filepath=str(fbx_file))
            char_obj = bpy.context.selected_objects[0] if bpy.context.selected_objects else None

    if not char_obj:
        return

    char_obj.location = Vector(actor_state["position_xyz"])
    char_obj.rotation_euler = Euler([math.radians(x) for x in actor_state["rotation_euler_deg"]], 'XYZ')

    # Nạp chuyển động cơ thể từ thư viện Mixamo nếu file tồn tại
    mixamo_path = Path(actor_state.get("mixamo_animation", ""))
    if mixamo_path.exists() and char_obj.type == 'ARMATURE':
        bpy.ops.import_scene.fbx(filepath=str(mixamo_path))
        imported_arms = [o for o in bpy.context.selected_objects if o.type == 'ARMATURE' and o != char_obj]
        if imported_arms and imported_arms[0].animation_data and imported_arms[0].animation_data.action:
            if not char_obj.animation_data:
                char_obj.animation_data_create()
            char_obj.animation_data.action = imported_arms[0].animation_data.action
            for temp_ob in imported_arms:
                bpy.data.objects.remove(temp_ob, do_unlink=True)

    if not is_speaker or not viseme_json_path.exists():
        return

    viseme_data = json.loads(viseme_json_path.read_text(encoding="utf-8"))
    face_mesh = bpy.data.objects.get(char_cfg.get("face_mesh_name", ""))
    jaw_bone_name = char_cfg.get("jaw_bone_name", "Bone_Jaw")

    for cue in viseme_data.get("keyframes", []):
        f_start = cue["frame_start"]
        f_peak = cue["frame_peak"]
        jaw_val = float(cue["jaw_open"])
        weights = cue["weights"]

        # Điều khiển Shape Keys môi (shape_A, shape_O, shape_E, shape_M, shape_F)
        if face_mesh and face_mesh.type == 'MESH' and face_mesh.data.shape_keys:
            kb = face_mesh.data.shape_keys.key_blocks
            for shape_name, w_val in weights.items():
                if shape_name in kb:
                    kb[shape_name].value = float(w_val)
                    kb[shape_name].keyframe_insert(data_path="value", frame=f_peak)

        # Điều khiển Xương hàm (Jaw Bone) mở theo độ rộng nguyên âm
        if char_obj.type == 'ARMATURE' and jaw_bone_name in char_obj.pose.bones:
            jaw_bone = char_obj.pose.bones[jaw_bone_name]
            jaw_bone.rotation_mode = 'XYZ'
            jaw_bone.rotation_euler[0] = math.radians(jaw_val * 22.0)
            jaw_bone.keyframe_insert(data_path="rotation_euler", index=0, frame=f_start)
            jaw_bone.keyframe_insert(data_path="rotation_euler", index=0, frame=f_peak)

def main():
    args = get_cli_arguments()
    storyboard_path = Path(args["storyboard"])
    shot_id = args["shot-id"]

    storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
    meta = storyboard["project_meta"]
    scene_cfg = storyboard["scene"]
    characters_cfg = storyboard["characters"]
    shot = next(s for s in storyboard["shots"] if s["shot_id"] == shot_id)

    scene = bpy.context.scene
    fps = int(meta.get("fps", 24))
    scene.render.fps = fps
    scene.render.resolution_x = int(meta["resolution"][0])
    scene.render.resolution_y = int(meta["resolution"][1])
    scene.render.resolution_percentage = 100

    viseme_path = Path(shot["dialogue"]["viseme_json_path"])
    if viseme_path.exists():
        v_info = json.loads(viseme_path.read_text(encoding="utf-8"))
        scene.frame_start = 1
        # Render dư thêm 0.35 giây ở cuối cảnh để Tầng 4 thực hiện kỹ thuật cắt J-Cut / L-Cut mượt mà
        scene.frame_end = int(v_info["total_frames"]) + int(round(fps * 0.35))
    else:
        scene.frame_start = 1
        scene.frame_end = fps * 3

    for char_id, actor_state in shot["actors"].items():
        apply_mixamo_and_lipsync_keyframes(
            char_id=char_id,
            char_cfg=characters_cfg.get(char_id, {}),
            actor_state=actor_state,
            viseme_json_path=viseme_path,
            is_speaker=(char_id == shot["speaker"])
        )

    setup_camera_dof_and_rack_focus(scene, shot, characters_cfg, fps)

    spk_pos = Vector(shot["actors"][shot["speaker"]]["position_xyz"])
    cam_pos = Vector(shot["camera"]["location_xyz"])
    setup_three_point_lighting(spk_pos, cam_pos)

    setup_eevee_cinematic_pipeline(scene, meta, scene_cfg)
    enforce_4gb_vram_discipline(scene_cfg, max_tex_res=int(meta.get("max_texture_size", 2048)))

    out_video = Path(shot["transition"]["raw_render_path"]).resolve()
    out_video.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(out_video)
    scene.render.image_settings.file_format = 'FFMPEG'
    scene.render.ffmpeg.format = 'MPEG4'
    scene.render.ffmpeg.codec = 'H264'
    scene.render.ffmpeg.constant_rate_factor = 'HIGH'

    bpy.ops.render.render(animation=True)

if __name__ == "__main__":
    main()
