from pathlib import Path
from src.stage3_blender_eevee import render_shot

def test_stage3_render_script_contains_all_5_p2000_optimizations():
    source_code = Path(render_shot.__file__).read_text(encoding="utf-8")

    # 1. Ống kính 50-85mm + Xóa phông f/2.0 + Rack Focus
    assert "cam_data.dof.use_dof = True" in source_code
    assert "cam_data.dof.focus_object" in source_code
    # 2. Volumetrics & 3-Point Lighting
    assert "use_volumetric_lighting" in source_code
    assert "CINE_3PT_KEY" in source_code and "CINE_3PT_FILL" in source_code and "CINE_3PT_RIM" in source_code
    # 3. SSR & GTAO
    assert "eevee.use_ssr = True" in source_code
    assert "eevee.use_gtao = True" in source_code
    # 4. Hệ màu chuẩn rạp AgX - High Contrast
    assert "AgX - High Contrast" in source_code
    # 5. Kỷ luật 4GB VRAM: Giới hạn Texture 2048 & Instancing
    assert "img.scale(new_w, new_h)" in source_code
    assert "inst_obj.data = src_obj.data" in source_code
