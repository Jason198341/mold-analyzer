#!/usr/bin/env python3
"""Mold Analyzer - CAD 파일 기반 금형 사전 검토 도구.

사용법:
    python analyze.py part.step                  STEP 분석
    python analyze.py part.igs                   IGES 분석
    python analyze.py part.stl                   STL 분석
    python analyze.py part.3dxml                 3DXML 분석
    python analyze.py part.igs --axis x          X축 열림 방향
    python analyze.py part.stl --min-draft 2.0   최소 구배각 기준

지원 형식: .step, .stp, .igs, .iges, .stl, .3dxml
"""

import argparse
import os
import sys
import time
import io

# Windows 콘솔 UTF-8 출력 지원
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


def main():
    parser = argparse.ArgumentParser(
        description="금형 분석 도구 - CAD 파일의 구배각, 파팅라인, 언더컷을 분석합니다.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
지원 형식:
  .step, .stp    STEP (B-Rep) - 완전 분석
  .igs, .iges    IGES (B-Rep) - 완전 분석
  .stl           STL (Mesh)   - 구배각 분석 (면 유형 구분 불가)
  .3dxml         3DXML (Mesh) - 구배각 분석 (면 유형 구분 불가)

예시:
  python analyze.py part.step                    기본 분석
  python analyze.py part.igs --axis x            X축 방향 금형
  python analyze.py part.stl --min-draft 2.0     최소 구배 2도 기준
  python analyze.py part.3dxml -o my_report      출력 파일명 지정
        """,
    )
    parser.add_argument("input", help="CAD 파일 경로 (.step/.stp/.igs/.iges/.stl/.3dxml)")
    parser.add_argument("-o", "--output", help="출력 HTML 파일명 (확장자 제외)", default=None)
    parser.add_argument("--axis", choices=["x", "y", "z"], default="z",
                        help="금형 열림 방향 (기본: z)")
    parser.add_argument("--min-draft", type=float, default=1.0,
                        help="최소 구배각 기준 (기본: 1.0도)")
    parser.add_argument("--mesh-quality", type=float, default=0.1,
                        help="메시 정밀도 - 작을수록 정밀 (기본: 0.1)")
    parser.add_argument("--pdf", action="store_true",
                        help="PDF 리포트도 함께 생성")

    args = parser.parse_args()

    # 입력 파일 확인
    if not os.path.exists(args.input):
        print(f"  파일을 찾을 수 없습니다: {args.input}")
        sys.exit(1)

    # 출력 경로 설정
    if args.output:
        output_path = args.output if args.output.endswith(".html") else args.output + ".html"
    else:
        base = os.path.splitext(os.path.basename(args.input))[0]
        output_path = f"{base}_mold_report.html"

    # 열림 방향 설정
    from OCP.gp import gp_Dir
    axis_map = {
        "x": gp_Dir(1, 0, 0),
        "y": gp_Dir(0, 1, 0),
        "z": gp_Dir(0, 0, 1),
    }
    opening_dir = axis_map[args.axis]
    axis_label = {"x": "X+", "y": "Y+", "z": "Z+"}[args.axis]

    print("=" * 60)
    print("  Mold Analyzer - 금형 사전 검토 도구")
    print("=" * 60)
    print(f"  입력 파일:   {args.input}")
    print(f"  열림 방향:   {axis_label}")
    print(f"  최소 구배:   {args.min_draft}")
    print(f"  출력 파일:   {output_path}")
    print("=" * 60)

    total_steps = 10 if args.pdf else 9

    # ── Step 1: CAD 파일 읽기 ─────────────────────
    print(f"\n[1/{total_steps}] CAD 파일 읽는 중...")
    t0 = time.time()

    from core.reader import read_cad_file, extract_faces, get_bounding_box, get_shape_properties

    shape, format_name, format_info = read_cad_file(args.input)
    faces = extract_faces(shape)
    bbox = get_bounding_box(shape)
    shape_props = get_shape_properties(shape)

    print(f"  > 형식: {format_name}")
    print(f"  > {format_info}")
    print(f"  > {len(faces)}개 면 추출 ({time.time() - t0:.1f}s)")
    print(f"  > 크기: {bbox['dx']:.1f} x {bbox['dy']:.1f} x {bbox['dz']:.1f} mm")
    print(f"  > 체적: {shape_props['volume_mm3']:.1f} mm3")

    # ── Step 2: 구배각 분석 ─────────────────────────
    print(f"\n[2/{total_steps}] 구배각 분석 중...")
    t1 = time.time()

    from core.analysis import analyze_all_faces, summarize

    face_results = analyze_all_faces(faces, opening_dir)
    summary = summarize(face_results)

    cats = summary["categories"]
    print(f"  > 분석 완료 ({time.time() - t1:.1f}s)")
    print(f"  > 양호: {cats.get('good', 0)}  |  경계: {cats.get('marginal', 0)}  |  "
          f"불충분: {cats.get('insufficient', 0)}  |  없음: {cats.get('zero', 0)}")

    # ── Step 3: 파팅라인 추정 ───────────────────────
    print(f"\n[3/{total_steps}] 파팅라인 추정 중...")
    t2 = time.time()

    from core.analysis import estimate_parting_line, axis_index_from_dir

    parting_info = estimate_parting_line(shape, faces, face_results, opening_dir)
    ax_idx = parting_info["axis_index"]
    ax_name = parting_info["axis_name"]

    print(f"  > 추정 파팅라인 {ax_name} = {parting_info['parting_z']:.2f} mm ({time.time() - t2:.1f}s)")
    print(f"  > Cavity: {parting_info['upper_face_count']}면  |  "
          f"Core: {parting_info['lower_face_count']}면  |  "
          f"수직: {parting_info['vertical_face_count']}면")

    # ── Step 4: 언더컷 검출 ─────────────────────────
    print(f"\n[4/{total_steps}] 언더컷 검출 중...")
    t3 = time.time()

    from core.analysis import detect_undercuts

    undercuts = detect_undercuts(face_results, parting_info["parting_z"], opening_dir)

    if undercuts:
        print(f"  ! {len(undercuts)}개 언더컷 의심 영역 발견! ({time.time() - t3:.1f}s)")
        for uc in undercuts[:5]:
            print(f"    - Face #{uc['face_id']}: {uc['reason']}")
        if len(undercuts) > 5:
            print(f"    ... 외 {len(undercuts) - 5}개")
    else:
        print(f"  > 언더컷 없음 ({time.time() - t3:.1f}s)")

    # ── Step 5: 벽 두께 분석 ─────────────────────────
    print(f"\n[5/{total_steps}] 벽 두께 분석 중...")
    t_thick = time.time()

    from core.analysis import analyze_wall_thickness

    thickness_data = analyze_wall_thickness(shape, faces, n_samples=3)

    if thickness_data["total_samples"] > 0:
        print(f"  > 측정 완료 ({time.time() - t_thick:.1f}s)")
        print(f"  > 최소: {thickness_data['min_thickness']:.2f}mm | "
              f"최대: {thickness_data['max_thickness']:.2f}mm | "
              f"평균: {thickness_data['avg_thickness']:.2f}mm")
        if thickness_data["warnings"]:
            for w in thickness_data["warnings"]:
                print(f"  ! {w}")
    else:
        print(f"  > 벽 두께 측정 불가 ({time.time() - t_thick:.1f}s)")

    # ── Step 6: 슬라이드 코어 분석 ──────────────────
    print(f"\n[6/{total_steps}] 슬라이드 코어 분석 중...")
    t_slide = time.time()

    from core.slide_core import analyze_slides

    slides, mold_layout = analyze_slides(
        undercuts, face_results, bbox, parting_info["parting_z"],
        axis_index=ax_idx
    )

    if slides:
        print(f"  > {len(slides)}개 슬라이드/경사코어 제안 ({time.time() - t_slide:.1f}s)")
        for s in slides:
            print(f"    [{s['id']}] {s['core_type_kr']} | 방향: {s['direction_name']} | "
                  f"이동량: {s['stroke']:.1f}mm | 면: {s['face_count']}개")
        print(f"  > 금형 복잡도: {mold_layout['complexity']}")
    else:
        print(f"  > 슬라이드 불필요 ({time.time() - t_slide:.1f}s)")

    # ── Step 7: 3D 메시 추출 ────────────────────────
    print(f"\n[7/{total_steps}] 3D 메시 생성 중...")
    t4 = time.time()

    from core.mesh import extract_mesh, extract_parting_line_points, mesh_to_json

    mesh_data = extract_mesh(shape, face_results, args.mesh_quality, thickness_data)
    bbox_d_keys = ["dx", "dy", "dz"]
    parting_points = extract_parting_line_points(
        shape, parting_info["parting_z"],
        tolerance=bbox[bbox_d_keys[ax_idx]] * 0.02,
        axis_index=ax_idx
    )
    mesh_json = mesh_to_json(mesh_data, parting_points)

    print(f"  > {mesh_data['triangle_count']}개 삼각형 생성 ({time.time() - t4:.1f}s)")

    # ── Step 8: 리포트 생성 ─────────────────────────
    print(f"\n[8/{total_steps}] HTML 리포트 생성 중...")
    t5 = time.time()

    from core.report import generate_report

    filename = os.path.basename(args.input)
    generate_report(
        filename=filename,
        shape_props=shape_props,
        bbox=bbox,
        summary=summary,
        face_results=face_results,
        undercuts=undercuts,
        parting_info=parting_info,
        mesh_json=mesh_json,
        slides=slides,
        mold_layout=mold_layout,
        thickness_data=thickness_data,
        output_path=output_path,
        axis_name=ax_name,
        axis_index=ax_idx,
    )

    total_time = time.time() - t0
    print(f"  > 리포트 저장: {output_path} ({time.time() - t5:.1f}s)")

    # ── Step 9: PDF 리포트 (옵션) ────────────────────
    pdf_path = None
    if args.pdf:
        print(f"\n[9/{total_steps}] PDF 리포트 생성 중...")
        t6 = time.time()

        from core.report import generate_pdf_report

        pdf_path = output_path.replace(".html", ".pdf")
        generate_pdf_report(
            filename=filename,
            shape_props=shape_props,
            bbox=bbox,
            summary=summary,
            face_results=face_results,
            undercuts=undercuts,
            parting_info=parting_info,
            slides=slides,
            mold_layout=mold_layout,
            thickness_data=thickness_data,
            output_path=pdf_path,
        )
        print(f"  > PDF 저장: {pdf_path} ({time.time() - t6:.1f}s)")
        total_time = time.time() - t0

    # ── 최종 요약 ───────────────────────────────────
    print("\n" + "=" * 60)
    print("  분석 완료 요약")
    print("=" * 60)
    print(f"  형식:        {format_name}")
    print(f"  전체 면:     {summary['total_faces']}개")
    print(f"  평균 구배각: {summary['avg_draft_overall']:.1f}")
    print(f"  최소 구배각: {summary['min_draft_overall']:.1f}")
    print(f"  언더컷:      {len(undercuts)}개")
    print(f"  슬라이드:    {mold_layout['total_slides']}개")
    print(f"  벽 두께:     {thickness_data['min_thickness']:.2f} ~ {thickness_data['max_thickness']:.2f}mm")
    print(f"  금형 복잡도: {mold_layout['complexity']}")
    print(f"  총 소요시간: {total_time:.1f}초")
    print(f"  리포트:      {os.path.abspath(output_path)}")
    if pdf_path:
        print(f"  PDF:         {os.path.abspath(pdf_path)}")
    print("=" * 60)

    # 문제가 있으면 경고
    problem_faces = cats.get("insufficient", 0) + cats.get("zero", 0)
    if problem_faces > 0 or undercuts:
        print(f"\n  [!] 주의사항:")
        if problem_faces > 0:
            print(f"    - {problem_faces}개 면의 구배각이 {args.min_draft} 미만입니다.")
            print(f"      -> 이형 불량 또는 금형 마모의 원인이 될 수 있습니다.")
        if undercuts:
            print(f"    - {len(undercuts)}개 영역에서 언더컷이 의심됩니다.")
            print(f"      -> 슬라이드 코어/경사 코어 적용을 검토하세요.")
        print()
    else:
        print(f"\n  [OK] 금형 성형성 양호 - 주요 문제 없음\n")


if __name__ == "__main__":
    main()
