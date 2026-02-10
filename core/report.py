"""HTML 리포트 생성 모듈.

분석 결과를 자기완결적 HTML 파일로 출력합니다.
three.js로 3D 모델을 렌더링하고, 구배각별 색상 코딩을 표시합니다.
"""

import html
import json
from datetime import datetime


def generate_report(
    filename: str,
    shape_props: dict,
    bbox: dict,
    summary: dict,
    face_results: list,
    undercuts: list,
    parting_info: dict,
    mesh_json: str,
    slides: list = None,
    mold_layout: dict = None,
    thickness_data: dict = None,
    output_path: str = "report.html",
) -> str:
    """HTML 분석 리포트를 생성합니다."""

    # 면 분류별 통계 행
    cat_labels = {
        "good": ("양호 (3°+)", "#33cc55"),
        "marginal": ("경계 (1~3°)", "#ffdd00"),
        "insufficient": ("불충분 (<1°)", "#ff6600"),
        "zero": ("구배 없음 (0°)", "#ff1a1a"),
        "horizontal": ("수평면", "#9999cc"),
        "unknown": ("분석 불가", "#888888"),
    }

    category_rows = ""
    for cat, (label, color) in cat_labels.items():
        count = summary["categories"].get(cat, 0)
        if count > 0:
            category_rows += f"""
            <tr>
                <td><span class="dot" style="background:{color}"></span> {label}</td>
                <td>{count}</td>
            </tr>"""

    # 면 유형별 통계 행
    surface_rows = ""
    for stype, count in summary["surface_types"].items():
        surface_rows += f"<tr><td>{html.escape(stype)}</td><td>{count}</td></tr>"

    # 언더컷 행
    undercut_rows = ""
    if undercuts:
        for uc in undercuts:
            cx, cy, cz = uc["center"]
            undercut_rows += f"""
            <tr>
                <td>Face #{uc['face_id']}</td>
                <td>{html.escape(uc['surface_type'])}</td>
                <td>{uc['avg_draft']:.1f}°</td>
                <td>({cx:.1f}, {cy:.1f}, {cz:.1f})</td>
                <td>{html.escape(uc['reason'])}</td>
            </tr>"""
    else:
        undercut_rows = '<tr><td colspan="5">언더컷이 검출되지 않았습니다.</td></tr>'

    # 면 상세 테이블 (구배각 기준 오름차순)
    sorted_faces = sorted(face_results, key=lambda r: r["avg_draft"])
    face_detail_rows = ""
    for r in sorted_faces[:50]:  # 상위 50개만
        cat = r["draft_category"]
        color = cat_labels.get(cat, ("", "#888"))[1]
        face_detail_rows += f"""
        <tr style="border-left: 4px solid {color}">
            <td>{r['face_id']}</td>
            <td>{html.escape(r['surface_type'])}</td>
            <td>{r['area']:.2f}</td>
            <td><strong>{r['min_draft']:.1f}°</strong></td>
            <td>{r['avg_draft']:.1f}°</td>
            <td>{r['max_draft']:.1f}°</td>
            <td>{html.escape(cat_labels.get(cat, (cat, ''))[0])}</td>
        </tr>"""

    # ── 슬라이드 코어 제안 HTML ────────────────────
    slides = slides or []
    mold_layout = mold_layout or {}

    slide_cards_html = ""
    slide_arrow_data = []  # three.js용 화살표 데이터

    if slides:
        type_colors = {
            "slide": ("#f59e0b", "amber"),
            "lifter": ("#8b5cf6", "violet"),
            "lifter_or_slide": ("#06b6d4", "cyan"),
        }

        for s in slides:
            color, _ = type_colors.get(s["core_type"], ("#888", "gray"))
            cx, cy, cz = s["center"]
            dx, dy, dz = s["direction_vector"]
            size = s["slide_size"]

            slide_cards_html += f"""
            <div class="card" style="border-left: 4px solid {color}">
              <h3 style="color:{color}; margin:0 0 0.75rem">
                Slide #{s['id']} - {html.escape(s['core_type_kr'])}
              </h3>
              <table>
                <tr><td>이동 방향</td><td><strong>{s['direction_name']}</strong> ({dx:.2f}, {dy:.2f}, {dz:.2f})</td></tr>
                <tr><td>이동 거리 (Stroke)</td><td><strong>{s['stroke']:.1f} mm</strong></td></tr>
                <tr><td>언더컷 깊이</td><td>{s['undercut_depth']:.1f} mm</td></tr>
                <tr><td>영향 면 수</td><td>{s['face_count']}개 (Face {', '.join(str(f) for f in s['face_ids'][:8])}{'...' if len(s['face_ids']) > 8 else ''})</td></tr>
                <tr><td>총 면적</td><td>{s['total_area']:.1f} mm2</td></tr>
                <tr><td>추정 크기 (W x H x L)</td><td>{size['width']:.0f} x {size['height']:.0f} x {size['length']:.0f} mm</td></tr>
                <tr><td>앵귤러 핀 각도</td><td>{s['angular_pin_angle']:.0f} deg</td></tr>
                <tr><td>위치 (X,Y,Z)</td><td>({cx:.1f}, {cy:.1f}, {cz:.1f})</td></tr>
                <tr><td>판정 사유</td><td>{html.escape(s['core_reason'])}</td></tr>
              </table>
            </div>"""

            # three.js 화살표용 데이터
            slide_arrow_data.append({
                "id": s["id"],
                "center": [cx, cy, cz],
                "direction": [dx, dy, dz],
                "stroke": s["stroke"],
                "type": s["core_type"],
            })

    slide_arrows_json = json.dumps(slide_arrow_data)

    # 금형 레이아웃 요약
    mold_summary_html = ""
    if mold_layout:
        est = mold_layout.get("estimated_mold_size", {})
        mold_summary_html = f"""
        <div class="card full-width" style="border: 2px solid var(--accent)">
          <h2 style="margin-top:0; color:var(--accent)">금형 설계 요약</h2>
          <div class="grid" style="grid-template-columns: 1fr 1fr 1fr">
            <div>
              <div class="stat-label">금형 복잡도</div>
              <div style="font-size:1.1rem; font-weight:700; color:#fff; margin-top:0.25rem">
                {html.escape(mold_layout.get('complexity', '-'))}
              </div>
              <div style="font-size:0.8rem; color:var(--text-dim); margin-top:0.25rem">
                {html.escape(mold_layout.get('complexity_detail', ''))}
              </div>
            </div>
            <div>
              <div class="stat-label">추정 금형 크기</div>
              <div style="font-size:1.1rem; font-weight:700; color:#fff; margin-top:0.25rem">
                {est.get('width', 0):.0f} x {est.get('depth', 0):.0f} x {est.get('height', 0):.0f} mm
              </div>
              <div style="font-size:0.8rem; color:var(--text-dim); margin-top:0.25rem">
                (부품 + 슬라이드 + 프레임 여유)
              </div>
            </div>
            <div>
              <div class="stat-label">최대 슬라이드 이동량</div>
              <div style="font-size:1.1rem; font-weight:700; color:#fff; margin-top:0.25rem">
                {mold_layout.get('max_stroke', 0):.1f} mm
              </div>
              <div style="font-size:0.8rem; color:var(--text-dim); margin-top:0.25rem">
                파팅라인 Z = {mold_layout.get('parting_z', 0):.1f} mm
              </div>
            </div>
          </div>
        </div>"""

    # ── 벽 두께 분석 HTML ─────────────────────────────
    thickness_data = thickness_data or {}
    thickness_html = ""
    if thickness_data.get("total_samples", 0) > 0:
        tw = thickness_data.get("warnings", [])
        tw_cards = ""
        if tw:
            tw_items = "".join(f"<li>{html.escape(w)}</li>" for w in tw)
            tw_cards = f"""
            <div class="alert" style="margin-bottom:1rem">
              <strong>벽 두께 경고</strong>
              <ul style="margin:0.5rem 0 0;padding-left:1.2rem">{tw_items}</ul>
            </div>"""

        # 히스토그램 SVG
        histo = thickness_data.get("histogram")
        histo_svg = ""
        if histo and histo.get("bins"):
            bins = histo["bins"]
            max_bin = max(bins) if bins else 1
            bar_w = 100 / len(bins)
            bars = ""
            for idx_b, cnt in enumerate(bins):
                h = cnt / max_bin * 80 if max_bin > 0 else 0
                x = idx_b * bar_w
                val = histo["min"] + (idx_b + 0.5) * histo["bin_size"]
                # 색상: <0.8 빨강, 0.8~1.5 주황, 1.5~3.0 초록, 3.0~4.0 노랑, >4.0 빨강
                if val < 0.8:
                    c = "#ff1a1a"
                elif val < 1.5:
                    c = "#ff8800"
                elif val < 3.0:
                    c = "#33cc55"
                elif val < 4.0:
                    c = "#ffdd00"
                else:
                    c = "#ff1a1a"
                bars += f'<rect x="{x}%" y="{90-h}%" width="{bar_w*0.8}%" height="{h}%" fill="{c}" rx="2"/>'
            histo_svg = f"""
            <div style="margin-top:1rem">
              <div style="font-size:0.8rem;color:var(--text-dim);margin-bottom:4px">두께 분포</div>
              <svg viewBox="0 0 100 100" style="width:100%;height:80px;background:rgba(0,0,0,0.2);border-radius:6px">
                {bars}
              </svg>
              <div style="display:flex;justify-content:space-between;font-size:0.7rem;color:var(--text-dim)">
                <span>{histo['min']:.1f}mm</span><span>{histo['max']:.1f}mm</span>
              </div>
            </div>"""

        thickness_html = f"""
<h2>벽 두께 분석</h2>
{tw_cards}
<div class="grid">
  <div class="card">
    <table>
      <tr><td>최소 두께</td><td><strong>{thickness_data['min_thickness']:.2f} mm</strong></td></tr>
      <tr><td>최대 두께</td><td><strong>{thickness_data['max_thickness']:.2f} mm</strong></td></tr>
      <tr><td>평균 두께</td><td>{thickness_data['avg_thickness']:.2f} mm</td></tr>
      <tr><td>두께비 (최대/최소)</td><td>{thickness_data['thickness_ratio']:.1f}:1</td></tr>
      <tr><td>측정 샘플 수</td><td>{thickness_data['total_samples']}개</td></tr>
    </table>
  </div>
  <div class="card">
    <div style="font-size:0.85rem;color:var(--text-dim)">
      <div><span class="dot" style="background:#ff1a1a"></span> &lt;0.8mm: 충전불량 위험</div>
      <div><span class="dot" style="background:#ff8800"></span> 0.8~1.5mm: 주의 필요</div>
      <div><span class="dot" style="background:#33cc55"></span> 1.5~3.0mm: 양호</div>
      <div><span class="dot" style="background:#ffdd00"></span> 3.0~4.0mm: 싱크마크 주의</div>
      <div><span class="dot" style="background:#ff1a1a"></span> &gt;4.0mm: 싱크마크 위험</div>
    </div>
    {histo_svg}
  </div>
</div>
"""

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    report_html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>금형 분석 리포트 - {html.escape(filename)}</title>
<style>
  :root {{
    --bg: #0f1219;
    --surface: #1a1f2e;
    --border: #2a3040;
    --text: #e0e0e0;
    --text-dim: #888;
    --accent: #6366f1;
    --good: #33cc55;
    --warn: #ffdd00;
    --bad: #ff4444;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: 'Segoe UI', -apple-system, sans-serif;
    line-height: 1.6;
    padding: 2rem;
  }}
  h1 {{
    font-size: 1.8rem;
    margin-bottom: 0.5rem;
    color: #fff;
  }}
  h2 {{
    font-size: 1.2rem;
    color: var(--accent);
    margin: 2rem 0 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border);
  }}
  .meta {{ color: var(--text-dim); font-size: 0.85rem; margin-bottom: 2rem; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }}
  .card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.5rem;
  }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
  th, td {{ padding: 0.5rem 0.75rem; text-align: left; }}
  th {{ color: var(--text-dim); font-weight: 500; border-bottom: 1px solid var(--border); }}
  tr:hover {{ background: rgba(99,102,241,0.05); }}
  .dot {{
    display: inline-block;
    width: 12px; height: 12px;
    border-radius: 50%;
    margin-right: 6px;
    vertical-align: middle;
  }}
  .stat-value {{ font-size: 1.5rem; font-weight: 700; color: #fff; }}
  .stat-label {{ font-size: 0.8rem; color: var(--text-dim); }}
  .stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 2rem; }}
  .stat-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1rem 1.25rem;
    text-align: center;
  }}
  #viewer {{
    width: 100%;
    height: 500px;
    background: #0a0d14;
    border-radius: 12px;
    border: 1px solid var(--border);
    margin-bottom: 2rem;
  }}
  .legend {{
    display: flex; gap: 1.5rem; flex-wrap: wrap;
    margin-bottom: 1rem; font-size: 0.8rem;
  }}
  .legend-item {{ display: flex; align-items: center; gap: 4px; }}
  .alert {{
    background: rgba(255,68,68,0.1);
    border: 1px solid rgba(255,68,68,0.3);
    border-radius: 8px;
    padding: 1rem;
    margin-bottom: 1rem;
  }}
  .full-width {{ grid-column: 1 / -1; }}
  .scroll-table {{ max-height: 400px; overflow-y: auto; }}
</style>
</head>
<body>

<h1>금형 분석 리포트</h1>
<div class="meta">
  파일: {html.escape(filename)} | 분석일: {now} | 열림 방향: Z+ (상방)
</div>

<div class="stats">
  <div class="stat-card">
    <div class="stat-value">{summary['total_faces']}</div>
    <div class="stat-label">전체 면 수</div>
  </div>
  <div class="stat-card">
    <div class="stat-value">{summary['avg_draft_overall']:.1f}°</div>
    <div class="stat-label">평균 구배각</div>
  </div>
  <div class="stat-card">
    <div class="stat-value">{summary['min_draft_overall']:.1f}°</div>
    <div class="stat-label">최소 구배각</div>
  </div>
  <div class="stat-card">
    <div class="stat-value">{len(undercuts)}</div>
    <div class="stat-label">언더컷 의심</div>
  </div>
</div>

<h2>3D 모델 시각화</h2>
<div class="legend">
  <div class="legend-item"><span class="dot" style="background:#33cc55"></span> 양호 (3°+)</div>
  <div class="legend-item"><span class="dot" style="background:#ffdd00"></span> 경계 (1~3°)</div>
  <div class="legend-item"><span class="dot" style="background:#ff6600"></span> 불충분 (<1°)</div>
  <div class="legend-item"><span class="dot" style="background:#ff1a1a"></span> 구배 없음</div>
  <div class="legend-item"><span class="dot" style="background:#9999cc"></span> 수평면</div>
  <div class="legend-item"><span class="dot" style="background:#44aaff"></span> 파팅라인 (추정)</div>
</div>
<div style="display:flex;align-items:center;gap:1.5rem;margin-bottom:8px">
  <span style="font-size:0.75rem;color:#666">키보드: ← → 금형 열기/닫기 | ↑ ↓ 슬라이드 코어 후퇴/전진</span>
  <button id="btn-toggle-color" style="background:var(--accent);color:#fff;border:none;border-radius:6px;padding:4px 14px;font-size:0.75rem;cursor:pointer;font-weight:600">색상: 구배각</button>
</div>
<div id="viewer"></div>

<div class="grid">
  <div class="card">
    <h2 style="margin-top:0">형상 정보</h2>
    <table>
      <tr><td>체적</td><td>{shape_props['volume_mm3']:.1f} mm³</td></tr>
      <tr><td>표면적</td><td>{shape_props['surface_area_mm2']:.1f} mm²</td></tr>
      <tr><td>크기 (X×Y×Z)</td><td>{bbox['dx']:.1f} × {bbox['dy']:.1f} × {bbox['dz']:.1f} mm</td></tr>
      <tr><td>추정 파팅라인 Z</td><td>{parting_info['parting_z']:.2f} mm</td></tr>
    </table>
  </div>

  <div class="card">
    <h2 style="margin-top:0">구배각 분류</h2>
    <table>
      <th>카테고리</th><th>면 수</th>
      {category_rows}
    </table>
  </div>

  <div class="card">
    <h2 style="margin-top:0">면 유형 분포</h2>
    <table>
      <th>유형</th><th>면 수</th>
      {surface_rows}
    </table>
  </div>

  <div class="card">
    <h2 style="margin-top:0">금형 분할 분석</h2>
    <table>
      <tr><td>상부 면 (Cavity)</td><td>{parting_info['upper_face_count']}개</td></tr>
      <tr><td>하부 면 (Core)</td><td>{parting_info['lower_face_count']}개</td></tr>
      <tr><td>수직 면 (PL 후보)</td><td>{parting_info['vertical_face_count']}개</td></tr>
    </table>
  </div>
</div>

{"" if not undercuts else '''
<h2>⚠ 언더컷 검출 결과</h2>
<div class="alert">
  <strong>''' + str(len(undercuts)) + '''개의 언더컷 의심 영역</strong>이 발견되었습니다.
  슬라이드 코어 또는 경사 코어 적용을 검토하세요.
</div>
'''}
<div class="card full-width">
  <table>
    <tr><th>Face</th><th>면 유형</th><th>구배각</th><th>위치 (X,Y,Z)</th><th>사유</th></tr>
    {undercut_rows}
  </table>
</div>

{thickness_html}

{mold_summary_html}

{"" if not slides else '''
<h2>슬라이드 코어 / 경사 코어 제안</h2>
<div class="legend" style="margin-bottom:1rem">
  <div class="legend-item"><span class="dot" style="background:#f59e0b"></span> 슬라이드 코어</div>
  <div class="legend-item"><span class="dot" style="background:#8b5cf6"></span> 경사 코어 (리프터)</div>
  <div class="legend-item"><span class="dot" style="background:#06b6d4"></span> 경사/슬라이드 선택</div>
</div>
<div class="grid">
''' + slide_cards_html + '''
</div>
'''}

<h2>면 상세 분석 (구배각 오름차순, 상위 50개)</h2>
<div class="card full-width scroll-table">
  <table>
    <tr>
      <th>Face #</th><th>면 유형</th><th>면적 (mm²)</th>
      <th>최소 구배</th><th>평균 구배</th><th>최대 구배</th><th>분류</th>
    </tr>
    {face_detail_rows}
  </table>
</div>

<script type="importmap">
{{
  "imports": {{
    "three": "https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.js",
    "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.170.0/examples/jsm/"
  }}
}}
</script>
<script type="module">
import * as THREE from 'three';
import {{ OrbitControls }} from 'three/addons/controls/OrbitControls.js';

const container = document.getElementById('viewer');
const width = container.clientWidth;
const height = container.clientHeight;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0a0d14);

const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 10000);
const renderer = new THREE.WebGLRenderer({{ antialias: true }});
renderer.setSize(width, height);
renderer.setPixelRatio(window.devicePixelRatio);
container.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;

// 조명
scene.add(new THREE.AmbientLight(0xffffff, 0.4));
const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
dirLight.position.set(1, 2, 3);
scene.add(dirLight);
const dirLight2 = new THREE.DirectionalLight(0xffffff, 0.3);
dirLight2.position.set(-2, -1, -1);
scene.add(dirLight2);

// 메시 데이터 로드
const meshData = {mesh_json};
const partingZ = {parting_info['parting_z']};
const slideData = {slide_arrows_json};
const bboxDz = {bbox['dz']};

// 금형 애니메이션 상태
let moldOpen = 0, slideOut = 0;
const MOLD_SPEED = Math.max(bboxDz * 0.015, 0.5);
const SLIDE_SPEED = 1.5;
const MAX_MOLD = bboxDz * 0.8;
const MAX_SLIDE = slideData.length > 0 ? Math.max(...slideData.map(s => s.stroke)) : 30;

const cavityGroup = new THREE.Group();
const coreGroup = new THREE.Group();
scene.add(cavityGroup);
scene.add(coreGroup);
const slideGroupList = [];
let viewRadius = 100;

if (meshData.positions && meshData.positions.length > 0) {{
  // Cavity(상부) / Core(하부) 분리 - 파팅라인 기준
  const cavP=[],cavC=[],cavN=[], corP=[],corC=[],corN=[];
  const triCnt = meshData.positions.length / 9;
  for (let t = 0; t < triCnt; t++) {{
    const b = t * 9;
    const avgZ = (meshData.positions[b+2] + meshData.positions[b+5] + meshData.positions[b+8]) / 3;
    const tg = avgZ > partingZ ? [cavP,cavC,cavN] : [corP,corC,corN];
    for (let v = 0; v < 9; v++) {{
      tg[0].push(meshData.positions[b+v]);
      tg[1].push(meshData.colors[b+v]);
      tg[2].push(meshData.normals[b+v]);
    }}
  }}

  function mkHalf(p, c, n, grp) {{
    if (!p.length) return;
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(p, 3));
    g.setAttribute('color', new THREE.Float32BufferAttribute(c, 3));
    g.setAttribute('normal', new THREE.Float32BufferAttribute(n, 3));
    grp.add(new THREE.Mesh(g, new THREE.MeshPhongMaterial({{
      vertexColors: true, side: THREE.DoubleSide, shininess: 40
    }})));
    grp.add(new THREE.Mesh(g, new THREE.MeshBasicMaterial({{
      color: 0x444466, wireframe: true, transparent: true, opacity: 0.08
    }})));
  }}
  mkHalf(cavP, cavC, cavN, cavityGroup);
  mkHalf(corP, corC, corN, coreGroup);

  // 카메라 위치 자동 설정
  const fullGeo = new THREE.BufferGeometry();
  fullGeo.setAttribute('position', new THREE.Float32BufferAttribute(meshData.positions, 3));
  fullGeo.computeBoundingSphere();
  const sphere = fullGeo.boundingSphere;
  const center = sphere.center;
  viewRadius = sphere.radius;
  camera.position.set(center.x + viewRadius * 2, center.y + viewRadius * 1.5, center.z + viewRadius * 2);
  controls.target.copy(center);

  // 파팅라인 표시
  if (meshData.parting_line && meshData.parting_line.length > 1) {{
    const pts = meshData.parting_line.map(p => new THREE.Vector3(p[0], p[1], p[2]));
    scene.add(new THREE.Points(
      new THREE.BufferGeometry().setFromPoints(pts),
      new THREE.PointsMaterial({{ color: 0x44aaff, size: 3 }})
    ));
  }}

  // 축 헬퍼
  const axH = new THREE.AxesHelper(viewRadius * 0.5);
  axH.position.copy(center);
  scene.add(axH);

  // 슬라이드 코어 (그룹화 - 애니메이션용)
  const typeColors = {{ slide: 0xf59e0b, lifter: 0x8b5cf6, lifter_or_slide: 0x06b6d4 }};

  slideData.forEach(s => {{
    const g = new THREE.Group();
    const dir = new THREE.Vector3(s.direction[0], s.direction[1], s.direction[2]).normalize();
    const len = Math.max(s.stroke, viewRadius * 0.4);
    const col = typeColors[s.type] || 0xf59e0b;

    g.add(new THREE.ArrowHelper(dir, new THREE.Vector3(), len, col, len * 0.25, len * 0.12));
    g.add(new THREE.Mesh(
      new THREE.SphereGeometry(viewRadius * 0.04, 8, 8),
      new THREE.MeshBasicMaterial({{ color: col }})
    ));

    const cv = document.createElement('canvas');
    cv.width = 64; cv.height = 64;
    const cx = cv.getContext('2d');
    cx.fillStyle = '#' + col.toString(16).padStart(6, '0');
    cx.beginPath(); cx.arc(32, 32, 28, 0, Math.PI * 2); cx.fill();
    cx.fillStyle = '#fff'; cx.font = 'bold 32px Arial';
    cx.textAlign = 'center'; cx.textBaseline = 'middle';
    cx.fillText(s.id.toString(), 32, 32);
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({{ map: new THREE.CanvasTexture(cv) }}));
    sp.position.set(0, 0, viewRadius * 0.12);
    sp.scale.set(viewRadius * 0.12, viewRadius * 0.12, 1);
    g.add(sp);

    const org = new THREE.Vector3(s.center[0], s.center[1], s.center[2]);
    g.position.copy(org);
    scene.add(g);
    slideGroupList.push({{ group: g, origin: org.clone(), dir: dir.clone(), stroke: s.stroke }});
  }});
}}

// ── 색상 토글 (구배각 ↔ 벽 두께) ──
let colorMode = 'draft';
const hasThickness = !!(meshData.thickness_colors && meshData.thickness_colors.length > 0);
const btnToggle = document.getElementById('btn-toggle-color');

// 두께 색상도 Cavity/Core 분리
const cavDraft=[], corDraft=[], cavThick=[], corThick=[];
if (hasThickness) {{
  const triCnt2 = meshData.positions.length / 9;
  for (let t = 0; t < triCnt2; t++) {{
    const b = t * 9;
    const avgZ = (meshData.positions[b+2] + meshData.positions[b+5] + meshData.positions[b+8]) / 3;
    const isUpper = avgZ > partingZ;
    for (let v = 0; v < 9; v++) {{
      (isUpper ? cavDraft : corDraft).push(meshData.colors[b+v]);
      (isUpper ? cavThick : corThick).push(meshData.thickness_colors[b+v]);
    }}
  }}
}}

// Phong 메시 참조 수집 (wireframe 제외)
const colorTargets = [];
function addColorTarget(grp, draftArr, thickArr) {{
  grp.children.forEach(c => {{
    if (c.isMesh && c.material && !c.material.wireframe) {{
      colorTargets.push({{ mesh: c, draft: draftArr, thick: thickArr }});
    }}
  }});
}}
if (hasThickness) {{
  addColorTarget(cavityGroup, cavDraft, cavThick);
  addColorTarget(coreGroup, corDraft, corThick);
}}

if (btnToggle && hasThickness) {{
  btnToggle.addEventListener('click', () => {{
    colorMode = colorMode === 'draft' ? 'thickness' : 'draft';
    btnToggle.textContent = colorMode === 'draft' ? '\\uc0c9\\uc0c1: \\uad6c\\ubc30\\uac01' : '\\uc0c9\\uc0c1: \\ubcbd \\ub450\\uaed8';
    btnToggle.style.background = colorMode === 'draft' ? '#6366f1' : '#f59e0b';
    colorTargets.forEach(ct => {{
      const src = colorMode === 'draft' ? ct.draft : ct.thick;
      ct.mesh.geometry.setAttribute('color', new THREE.Float32BufferAttribute(src, 3));
    }});
  }});
}} else if (btnToggle) {{
  btnToggle.style.display = 'none';
}}

// HUD 오버레이
const hud = document.createElement('div');
hud.style.cssText = 'position:absolute;bottom:12px;left:12px;background:rgba(15,18,25,0.88);border:1px solid rgba(99,102,241,0.3);border-radius:8px;padding:10px 14px;font:12px Segoe UI,sans-serif;color:#999;pointer-events:none;line-height:1.9;z-index:10';
hud.innerHTML = '<div style="color:#6366f1;font-weight:700;margin-bottom:2px">Mold Controls</div>'
  + '<div>\\u2190 \\u2192 <span style="color:#e0e0e0">\\uae08\\ud615 \\uc5f4\\uae30/\\ub2eb\\uae30</span> <span id="hud-mold" style="color:#33cc55;float:right;margin-left:12px">0%</span></div>'
  + '<div>\\u2191 \\u2193 <span style="color:#e0e0e0">\\uc2ac\\ub77c\\uc774\\ub4dc \\ud6c4\\ud1b4/\\uc804\\uc9c4</span> <span id="hud-slide" style="color:#f59e0b;float:right;margin-left:12px">0%</span></div>';
container.style.position = 'relative';
container.appendChild(hud);
const hudM = document.getElementById('hud-mold');
const hudS = document.getElementById('hud-slide');

function updateMold() {{
  cavityGroup.position.z = moldOpen;
  coreGroup.position.z = -moldOpen;
  slideGroupList.forEach(sg => {{
    const off = sg.dir.clone().multiplyScalar(slideOut / MAX_SLIDE * sg.stroke);
    sg.group.position.copy(sg.origin).add(off);
  }});
  if (hudM) hudM.textContent = Math.round(moldOpen / MAX_MOLD * 100) + '%';
  if (hudS) hudS.textContent = Math.round(slideOut / MAX_SLIDE * 100) + '%';
}}

// 키보드 제어
const keysDown = {{}};
document.addEventListener('keydown', e => {{
  if (['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)) {{
    keysDown[e.key] = true;
    e.preventDefault();
  }}
}});
document.addEventListener('keyup', e => {{ keysDown[e.key] = false; }});

function animate() {{
  requestAnimationFrame(animate);
  let mv = false;
  if (keysDown['ArrowRight']) {{ moldOpen = Math.min(moldOpen + MOLD_SPEED, MAX_MOLD); mv = true; }}
  if (keysDown['ArrowLeft'])  {{ moldOpen = Math.max(moldOpen - MOLD_SPEED, 0); mv = true; }}
  if (keysDown['ArrowUp'])    {{ slideOut = Math.min(slideOut + SLIDE_SPEED, MAX_SLIDE); mv = true; }}
  if (keysDown['ArrowDown'])  {{ slideOut = Math.max(slideOut - SLIDE_SPEED, 0); mv = true; }}
  if (mv) updateMold();
  controls.update();
  renderer.render(scene, camera);
}}
animate();

window.addEventListener('resize', () => {{
  const w = container.clientWidth;
  const h = container.clientHeight;
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h);
}});
</script>

<div style="margin-top:3rem; padding-top:1rem; border-top:1px solid var(--border); color:var(--text-dim); font-size:0.75rem; text-align:center">
  Mold Analyzer Report | Generated {now} | Open CASCADE + three.js
</div>

</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_html)

    return output_path


# ── PDF 리포트 생성 ─────────────────────────────────

def generate_pdf_report(
    filename: str,
    shape_props: dict,
    bbox: dict,
    summary: dict,
    face_results: list,
    undercuts: list,
    parting_info: dict,
    slides: list = None,
    mold_layout: dict = None,
    thickness_data: dict = None,
    output_path: str = "report.pdf",
) -> str:
    """PDF 분석 리포트를 생성합니다 (reportlab 사용)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, HRFlowable,
    )
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    # 한글 폰트 등록 (시스템 폰트 탐색)
    import os
    font_registered = False
    kr_font = "Helvetica"

    font_paths = [
        # Windows
        "C:/Windows/Fonts/malgun.ttf",
        "C:/Windows/Fonts/NanumGothic.ttf",
        "C:/Windows/Fonts/gulim.ttc",
        # macOS
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/Library/Fonts/NanumGothic.ttf",
        # Linux
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                pdfmetrics.registerFont(TTFont("KRFont", fp))
                kr_font = "KRFont"
                font_registered = True
                break
            except Exception:
                continue

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=20*mm, bottomMargin=20*mm,
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        "KRTitle", parent=styles["Title"],
        fontName=kr_font, fontSize=18, spaceAfter=12,
    ))
    styles.add(ParagraphStyle(
        "KRH2", parent=styles["Heading2"],
        fontName=kr_font, fontSize=13, spaceBefore=16, spaceAfter=8,
        textColor=colors.HexColor("#4444aa"),
    ))
    styles.add(ParagraphStyle(
        "KRBody", parent=styles["Normal"],
        fontName=kr_font, fontSize=9, leading=13,
    ))
    styles.add(ParagraphStyle(
        "KRSmall", parent=styles["Normal"],
        fontName=kr_font, fontSize=7.5, leading=10,
        textColor=colors.grey,
    ))

    story = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ─── Page 1: 요약 ───
    story.append(Paragraph("Mold Analyzer Report", styles["KRTitle"]))
    story.append(Paragraph(
        f"File: {filename} | Date: {now}", styles["KRSmall"]
    ))
    story.append(Spacer(1, 8*mm))

    # 형상 정보 테이블
    story.append(Paragraph("1. Shape Information", styles["KRH2"]))

    info_data = [
        ["Volume", f"{shape_props['volume_mm3']:.1f} mm\u00b3"],
        ["Surface Area", f"{shape_props['surface_area_mm2']:.1f} mm\u00b2"],
        ["Bounding Box", f"{bbox['dx']:.1f} x {bbox['dy']:.1f} x {bbox['dz']:.1f} mm"],
        ["Parting Line Z", f"{parting_info['parting_z']:.2f} mm ({parting_info.get('parting_method', 'histogram')})"],
        ["Total Faces", f"{summary['total_faces']}"],
    ]
    t = Table(info_data, colWidths=[50*mm, 110*mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), kr_font),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f0f8")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 6*mm))

    # 구배각 요약
    story.append(Paragraph("2. Draft Angle Summary", styles["KRH2"]))

    cat_labels_pdf = {
        "good": "Good (3\u00b0+)",
        "marginal": "Marginal (1~3\u00b0)",
        "insufficient": "Insufficient (<1\u00b0)",
        "zero": "No Draft (0\u00b0)",
        "horizontal": "Horizontal",
    }
    draft_data = [["Category", "Count"]]
    for cat, label in cat_labels_pdf.items():
        count = summary["categories"].get(cat, 0)
        if count > 0:
            draft_data.append([label, str(count)])

    draft_data.append(["Avg Draft", f"{summary['avg_draft_overall']:.1f}\u00b0"])
    draft_data.append(["Min Draft", f"{summary['min_draft_overall']:.1f}\u00b0"])
    draft_data.append(["Weighted Avg", f"{summary.get('weighted_avg_draft', 0):.1f}\u00b0"])

    t2 = Table(draft_data, colWidths=[60*mm, 100*mm])
    t2.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), kr_font),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4444aa")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t2)
    story.append(Spacer(1, 6*mm))

    # 언더컷
    story.append(Paragraph("3. Undercut Detection", styles["KRH2"]))
    if undercuts:
        story.append(Paragraph(
            f"<b>{len(undercuts)} undercut region(s) detected.</b>",
            styles["KRBody"],
        ))
        uc_data = [["Face #", "Type", "Draft", "Position", "Reason"]]
        for uc in undercuts[:20]:
            cx, cy, cz = uc["center"]
            uc_data.append([
                str(uc["face_id"]),
                uc["surface_type"][:15],
                f"{uc['avg_draft']:.1f}\u00b0",
                f"({cx:.0f},{cy:.0f},{cz:.0f})",
                uc["reason"][:30],
            ])
        t3 = Table(uc_data, colWidths=[15*mm, 30*mm, 15*mm, 35*mm, 65*mm])
        t3.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), kr_font),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#aa4444")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("PADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t3)
    else:
        story.append(Paragraph("No undercuts detected.", styles["KRBody"]))

    # ─── Page 2: 슬라이드 + 두께 ───
    story.append(PageBreak())

    slides = slides or []
    mold_layout = mold_layout or {}

    story.append(Paragraph("4. Slide Core Recommendations", styles["KRH2"]))
    if slides:
        slide_data = [["#", "Type", "Direction", "Stroke", "Depth", "Faces"]]
        for s in slides:
            slide_data.append([
                str(s["id"]),
                s["core_type_kr"][:10],
                s["direction_name"],
                f"{s['stroke']:.1f}mm",
                f"{s['undercut_depth']:.1f}mm",
                str(s["face_count"]),
            ])
        ts = Table(slide_data, colWidths=[10*mm, 25*mm, 30*mm, 25*mm, 25*mm, 15*mm])
        ts.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), kr_font),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#b58900")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("PADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(ts)

        if mold_layout:
            story.append(Spacer(1, 4*mm))
            story.append(Paragraph(
                f"Mold Complexity: <b>{mold_layout.get('complexity', '-')}</b> | "
                f"Max Stroke: {mold_layout.get('max_stroke', 0):.1f}mm",
                styles["KRBody"],
            ))
    else:
        story.append(Paragraph("No slide cores required.", styles["KRBody"]))

    story.append(Spacer(1, 6*mm))

    # 벽 두께
    thickness_data = thickness_data or {}
    story.append(Paragraph("5. Wall Thickness Analysis", styles["KRH2"]))
    if thickness_data.get("total_samples", 0) > 0:
        thick_info = [
            ["Min Thickness", f"{thickness_data['min_thickness']:.2f} mm"],
            ["Max Thickness", f"{thickness_data['max_thickness']:.2f} mm"],
            ["Avg Thickness", f"{thickness_data['avg_thickness']:.2f} mm"],
            ["Thickness Ratio", f"{thickness_data['thickness_ratio']:.1f}:1"],
            ["Samples", f"{thickness_data['total_samples']}"],
        ]
        tt = Table(thick_info, colWidths=[50*mm, 110*mm])
        tt.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), kr_font),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f8f0")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("PADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(tt)

        # 경고 표시
        for w in thickness_data.get("warnings", []):
            story.append(Spacer(1, 2*mm))
            story.append(Paragraph(f"WARNING: {w}", ParagraphStyle(
                "Warn", parent=styles["KRBody"],
                textColor=colors.HexColor("#cc0000"), fontSize=9,
            )))
    else:
        story.append(Paragraph("Wall thickness measurement not available.", styles["KRBody"]))

    story.append(Spacer(1, 8*mm))

    # 면 상세 (상위 30개)
    story.append(Paragraph("6. Face Detail (Top 30 by Draft)", styles["KRH2"]))
    sorted_faces = sorted(face_results, key=lambda r: r["avg_draft"])
    fd_data = [["#", "Type", "Area", "Min\u00b0", "Avg\u00b0", "Max\u00b0", "Cat."]]
    for r in sorted_faces[:30]:
        fd_data.append([
            str(r["face_id"]),
            r["surface_type"][:12],
            f"{r['area']:.1f}",
            f"{r['min_draft']:.1f}",
            f"{r['avg_draft']:.1f}",
            f"{r['max_draft']:.1f}",
            r["draft_category"][:8],
        ])
    tf = Table(fd_data, colWidths=[12*mm, 28*mm, 18*mm, 16*mm, 16*mm, 16*mm, 20*mm])
    tf.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), kr_font),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#444466")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dddddd")),
        ("PADDING", (0, 0), (-1, -1), 3),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f8fc")]),
    ]))
    story.append(tf)

    # 푸터
    story.append(Spacer(1, 10*mm))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#cccccc")))
    story.append(Paragraph(
        f"Mold Analyzer Report | {now} | Open CASCADE",
        styles["KRSmall"],
    ))

    doc.build(story)
    return output_path
