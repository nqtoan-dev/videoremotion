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
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parsed = {}
    for i in range(0, len(argv), 2):
        if i + 1 < len(argv):
            parsed[argv[i].lstrip("-")] = argv[i + 1]
    return parsed


def is_valid_binary_fbx(fbx_path: Path) -> bool:
    if not fbx_path.exists() or fbx_path.stat().st_size < 64:
        return False
    head = fbx_path.read_bytes()[:24]
    return b"CINE_CODE_PLACEHOLDER" not in head


def build_procedural_studio_and_character_if_needed(char_id: str, char_cfg: dict, actor_state: dict):
    """
    Khi file .blend hoặc .fbx trên đĩa chỉ là placeholder (CINE_CODE_PLACEHOLDER),
    tự động khởi tạo bối cảnh Studio 3D và nhân vật 3D có sẵn Xương hàm + Shape Keys (A,O,E,M,F) bằng bpy.
    """
    if bpy is None:
        return None

    # 1. Tạo sàn và tường Studio nếu cảnh đang trống
    if "Studio_Floor" not in bpy.data.objects:
        bpy.ops.mesh.primitive_plane_add(size=14.0, location=(0.0, 0.0, 0.0))
        floor = bpy.context.active_object
        floor.name = "Studio_Floor"
        mat_floor = bpy.data.materials.new("Mat_Studio_Floor")
        mat_floor.use_nodes = True
        bsdf = mat_floor.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (0.05, 0.06, 0.08, 1.0)
            bsdf.inputs["Roughness"].default_value = 0.25
        floor.data.materials.append(mat_floor)

    if "Prop_Chair_Master" not in bpy.data.objects:
        bpy.ops.mesh.primitive_cube_add(size=0.65, location=(0.0, 3.0, 0.35))
        chair = bpy.context.active_object
        chair.name = "Prop_Chair_Master"

    # 2. Tạo nhân vật 3D có Shape Keys khẩu hình nếu chưa có trong cảnh
    arm_name = char_cfg.get("armature_name", char_id)
    face_mesh_name = char_cfg.get("face_mesh_name", f"Mesh_Head_{char_id}")
    if face_mesh_name in bpy.data.objects:
        return bpy.data.objects.get(arm_name) or bpy.data.objects.get(face_mesh_name)

    pos = Vector(actor_state["position_xyz"])
    height_m = float(char_cfg.get("height_m", 1.72))

    # Tạo thân nhân vật
    bpy.ops.mesh.primitive_cylinder_add(radius=0.24, depth=height_m * 0.72, location=(pos.x, pos.y, height_m * 0.36))
    body_obj = bpy.context.active_object
    body_obj.name = f"Body_{char_id}"

    # Tạo đầu nhân vật kèm Shape Keys khẩu hình (shape_A, shape_O, shape_E, shape_M, shape_F)
    head_z = height_m * 0.88
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.19, location=(pos.x, pos.y, head_z))
    head_obj = bpy.context.active_object
    head_obj.name = face_mesh_name

    mat_skin = bpy.data.materials.new(f"Mat_{char_id}")
    mat_skin.use_nodes = True
    bsdf = mat_skin.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        color = (0.22, 0.52, 0.85, 1.0) if "MINH" in char_id else (0.85, 0.38, 0.32, 1.0)
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = 0.35
    head_obj.data.materials.append(mat_skin)
    body_obj.data.materials.append(mat_skin)

    # Thêm Shape Keys cho miệng
    head_obj.shape_key_add(name="Basis")
    for s_name in ["shape_A", "shape_O", "shape_E", "shape_M", "shape_F"]:
        head_obj.shape_key_add(name=s_name)

    body_obj.parent = head_obj
    body_obj.location = Vector((0.0, 0.0, -height_m * 0.52))
    return head_obj


def enforce_4gb_vram_discipline(scene_cfg: dict, max_tex_res: int = 2048):
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

    for prop_group in scene_cfg.get("instanced_props", []):
        src_name = prop_group.get("source_object_name")
        src_obj = bpy.data.objects.get(src_name)
        if not src_obj:
            continue
        for idx, loc in enumerate(prop_group.get("instance_locations", [])):
            inst_name = f"{src_name}_Instance_{idx:02d}"
            if inst_name not in bpy.data.objects:
                inst_obj = src_obj.copy()
                inst_obj.data = src_obj.data  # link=True
                inst_obj.name = inst_name
                bpy.context.collection.objects.link(inst_obj)
            bpy.data.objects[inst_name].location = Vector(loc)


def setup_eevee_cinematic_pipeline(scene, meta: dict, scene_cfg: dict):
    if bpy is None:
        return

    engines = [e.identifier for e in scene.render.bl_rna.properties['engine'].enum_items]
    scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engines else 'BLENDER_EEVEE'
    eevee = scene.eevee

    if hasattr(eevee, "use_volumetric_lighting"):
        eevee.use_volumetric_lighting = bool(scene_cfg.get("volumetric_lighting", True))
        eevee.use_volumetric_shadows = True
        eevee.volumetric_tile_size = '8'
    if hasattr(eevee, "use_soft_shadows"):
        eevee.use_soft_shadows = True
        eevee.shadow_cube_size = '1024'
        eevee.shadow_cascade_size = '2048'

    if hasattr(eevee, "use_ssr"):
        eevee.use_ssr = True
        eevee.use_ssr_refraction = True
        eevee.ssr_quality = 0.55
    if hasattr(eevee, "use_gtao"):
        eevee.use_gtao = True
        eevee.gtao_distance = 0.45

    if hasattr(eevee, "taa_render_samples"):
        eevee.taa_render_samples = 16

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
    is_speaker: bool,
):
    if bpy is None:
        return

    arm_name = char_cfg.get("armature_name", char_id)
    char_obj = bpy.data.objects.get(arm_name) or bpy.data.objects.get(char_id)

    if not char_obj:
        fbx_file = Path(char_cfg.get("fbx_path", ""))
        if is_valid_binary_fbx(fbx_file):
            bpy.ops.import_scene.fbx(filepath=str(fbx_file))
            char_obj = bpy.context.selected_objects[0] if bpy.context.selected_objects else None
        else:
            char_obj = build_procedural_studio_and_character_if_needed(char_id, char_cfg, actor_state)

    if not char_obj:
        return

    height_m = float(char_cfg.get("height_m", 1.72))
    pos = Vector(actor_state["position_xyz"])
    if char_obj.type == 'MESH':
        char_obj.location = Vector((pos.x, pos.y, height_m * 0.88))
    else:
        char_obj.location = pos
    char_obj.rotation_euler = Euler([math.radians(x) for x in actor_state["rotation_euler_deg"]], 'XYZ')

    mixamo_path = Path(actor_state.get("mixamo_animation", ""))
    if is_valid_binary_fbx(mixamo_path) and char_obj.type == 'ARMATURE':
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
    face_mesh = bpy.data.objects.get(char_cfg.get("face_mesh_name", "")) or char_obj
    jaw_bone_name = char_cfg.get("jaw_bone_name", "Bone_Jaw")

    for cue in viseme_data.get("keyframes", []):
        f_start = cue["frame_start"]
        f_peak = cue["frame_peak"]
        jaw_val = float(cue["jaw_open"])
        weights = cue["weights"]

        if face_mesh and face_mesh.type == 'MESH' and face_mesh.data.shape_keys:
            kb = face_mesh.data.shape_keys.key_blocks
            for shape_name, w_val in weights.items():
                if shape_name in kb:
                    kb[shape_name].value = float(w_val)
                    kb[shape_name].keyframe_insert(data_path="value", frame=f_peak)

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
            is_speaker=(char_id == shot["speaker"]),
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
