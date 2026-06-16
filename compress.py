"""
RO スプライト一括 WebP 変換スクリプト
======================================
使い方:
  python compress.py              # 全フォルダを変換（PNG → WebP に上書き）
  python compress.py --dry-run    # 変換せず圧縮率だけ計測
  python compress.py --folder MaleWait  # 特定フォルダのみ
  python compress.py --keep-png   # PNG を残したまま WebP を追加生成

変換後:
  - index.html の imgExt を 'webp' に変更してください
  - R2 へは WebP ファイルだけアップロードすれば OK です
"""

import os
import sys
import io
import time
import threading
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image

BASE_DIR = Path(__file__).parent / 'romaterial'

ACTION_FOLDERS = [
    'MaleWait', 'MaleWalk', 'MaleSit', 'MaleStand', 'MaleTake',
    'FemaleWait', 'FemaleWalk', 'FemaleSit', 'FemaleStand', 'FemaleTake',
]


# ──────────────────────────────────────────────
# 1ファイル変換処理
# ──────────────────────────────────────────────
def convert_one(png_path: Path, keep_png: bool = False) -> dict:
    webp_path = png_path.with_suffix('.webp')

    # すでに WebP が存在しスキップ対象の場合
    if webp_path.exists() and not keep_png:
        return {'skipped': True, 'orig': 0, 'new': 0}

    try:
        orig_size = png_path.stat().st_size
        img = Image.open(png_path).convert('RGBA')
        img.save(webp_path, 'WEBP', lossless=True, quality=100)
        new_size = webp_path.stat().st_size

        if not keep_png:
            png_path.unlink()   # 元 PNG を削除

        return {'skipped': False, 'orig': orig_size, 'new': new_size, 'path': str(png_path)}
    except Exception as e:
        return {'error': str(e), 'path': str(png_path), 'orig': 0, 'new': 0}


# ──────────────────────────────────────────────
# ドライラン: サンプル 20 件で圧縮率を計測
# ──────────────────────────────────────────────
def dry_run(folder_path: Path, sample_n: int = 20):
    pngs = list(folder_path.glob('*.png'))[:sample_n]
    if not pngs:
        print(f'  PNG なし: {folder_path}')
        return

    total_orig = total_new = 0
    print(f'\n[DRY RUN] {folder_path.name}  ({len(pngs)} サンプル)')
    for p in pngs:
        orig = p.stat().st_size
        img = Image.open(p).convert('RGBA')
        buf = io.BytesIO()
        img.save(buf, 'WEBP', lossless=True, quality=100)
        new = buf.tell()
        total_orig += orig
        total_new  += new
        print(f'  {p.name:<40} {orig//1024:>5}KB -> {new//1024:>5}KB  ({new*100//orig}%)')

    print(f'  サンプル合計: {total_orig//1024}KB -> {total_new//1024}KB'
          f'  圧縮率 {total_new*100//total_orig}%'
          f'  (削減 {(total_orig-total_new)//1024}KB)')


# ──────────────────────────────────────────────
# フォルダ単位の一括変換
# ──────────────────────────────────────────────
def convert_folder(folder_path: Path, keep_png: bool, workers: int):
    pngs = [p for p in folder_path.glob('*.png')]
    total = len(pngs)
    if total == 0:
        return {'total': 0, 'done': 0, 'orig_bytes': 0, 'new_bytes': 0, 'errors': 0}

    done = 0
    errors = 0
    orig_bytes = 0
    new_bytes  = 0
    lock = threading.Lock()
    t0 = time.time()

    def report(result):
        nonlocal done, errors, orig_bytes, new_bytes
        with lock:
            if result.get('error'):
                errors += 1
                print(f'\n  [ERROR] {result["path"]}: {result["error"]}')
            elif not result.get('skipped'):
                done      += 1
                orig_bytes += result['orig']
                new_bytes  += result['new']

            pct = done * 100 // total if total else 0
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0
            eta  = (total - done) / rate if rate > 0 else 0
            print(f'\r  {done:>6}/{total}  [{pct:>3}%]  '
                  f'{orig_bytes//1024//1024:>5}MB -> {new_bytes//1024//1024:>5}MB  '
                  f'ETA {int(eta//60)}m{int(eta%60):02d}s   ', end='', flush=True)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(convert_one, p, keep_png): p for p in pngs}
        for fut in as_completed(futures):
            report(fut.result())

    print()  # 改行
    return {
        'total': total,
        'done': done,
        'orig_bytes': orig_bytes,
        'new_bytes': new_bytes,
        'errors': errors,
    }


# ──────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description='RO sprite PNG -> WebP lossless 一括変換')
    parser.add_argument('--dry-run',   action='store_true', help='変換せずサンプル圧縮率を表示')
    parser.add_argument('--keep-png',  action='store_true', help='元 PNG を残す（WebP を追加生成）')
    parser.add_argument('--folder',    type=str,            help='特定フォルダのみ処理 (例: MaleWait)')
    parser.add_argument('--workers',   type=int, default=min(8, os.cpu_count() or 4),
                        help=f'並列ワーカー数 (デフォルト: {min(8, os.cpu_count() or 4)})')
    args = parser.parse_args()

    folders = [BASE_DIR / args.folder] if args.folder else [BASE_DIR / f for f in ACTION_FOLDERS]
    folders = [f for f in folders if f.is_dir()]

    if not folders:
        print(f'対象フォルダが見つかりません: {BASE_DIR}')
        sys.exit(1)

    # ── ドライラン ──────────────────────────
    if args.dry_run:
        print('=== DRY RUN モード（変換はしません）===')
        for folder in folders:
            dry_run(folder)
        return

    # ── 本変換 ─────────────────────────────
    mode = 'PNG を残して WebP を追加' if args.keep_png else 'PNG を WebP に置換（元 PNG 削除）'
    print(f'=== WebP lossless 変換 ===')
    print(f'モード  : {mode}')
    print(f'ワーカー: {args.workers} コア')
    print(f'フォルダ: {len(folders)} 個\n')

    grand_orig = grand_new = grand_done = grand_total = 0
    t_start = time.time()

    for folder in folders:
        png_count = len(list(folder.glob('*.png')))
        print(f'[{folder.name}]  {png_count} files ...')
        result = convert_folder(folder, args.keep_png, args.workers)
        grand_orig  += result['orig_bytes']
        grand_new   += result['new_bytes']
        grand_done  += result['done']
        grand_total += result['total']
        ratio = result['new_bytes'] * 100 // result['orig_bytes'] if result['orig_bytes'] else 0
        print(f'  完了: {result["done"]}/{result["total"]}  '
              f'{result["orig_bytes"]//1024//1024}MB -> {result["new_bytes"]//1024//1024}MB  '
              f'圧縮率 {ratio}%'
              + (f'  エラー: {result["errors"]}' if result["errors"] else ''))

    elapsed = time.time() - t_start
    ratio_all = grand_new * 100 // grand_orig if grand_orig else 0
    saved_gb  = (grand_orig - grand_new) / 1024**3

    print()
    print('=' * 55)
    print(f'完了  : {grand_done:,} / {grand_total:,} ファイル')
    print(f'変換前: {grand_orig/1024**3:.2f} GB')
    print(f'変換後: {grand_new/1024**3:.2f} GB')
    print(f'削減量: {saved_gb:.2f} GB  (圧縮率 {ratio_all}%)')
    print(f'所要時間: {int(elapsed//60)}分 {int(elapsed%60)}秒')
    print()
    if not args.keep_png:
        print('次のステップ: index.html の imgExt を "webp" に変更してください')


if __name__ == '__main__':
    main()
