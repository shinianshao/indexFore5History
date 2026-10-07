# -*- coding: utf-8 -*-
"""
生成中国两汉三国核心区域真实自然立体高精地形底图（High-Resolution Shaded Relief Basemap）
数据源：ESRI World Shaded Relief（全球权威山阴立体晕渲高程切片服务，纯自然山川地貌，无现代公路行政界线干扰）
范围：涵盖从陇西河西走廊（枹罕/金城/天水）到塞北幽燕辽西（蓟城/卢龙塞/白狼山/柳城），以及中原、江淮、荆襄、巴蜀全域
范围参数：经度 102.0°E ~ 122.5°E，纬度 26.5°N ~ 43.2°N
投影转换：Web 墨卡托 (EPSG:3857) -> 等角矩形投影 (Plate Carrée)
画质规格：Zoom 8 高精度超采样切片瓦片拼接，2000 x 1360 (对应 1000x680 之 2x Retina 超清画质)
色调调整：古典沉郁清晰水墨青绿山水晕渲（深山玄青深墨 + 纸白 #FAF7F0 + S型反差立体光影）
输出：
  - app/web/terrain_basemap.jpg
  - dist/terrain_basemap.jpg
"""
import concurrent.futures
import math
import os
import sys
import time
import urllib.request
from PIL import Image, ImageEnhance, ImageOps

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "app", "web")
DIST_DIR = os.path.join(ROOT, "dist")

FULL_LON_MIN = 102.0
FULL_LON_MAX = 122.5
FULL_LAT_MIN = 26.5
FULL_LAT_MAX = 43.2

OUT_WIDTH = 2000
OUT_HEIGHT = 1360  # 对应 1000x680 的 2x 超清 retina 比例

ZOOM = 8

def lon2tile(lon, z):
    return int((lon + 180.0) / 360.0 * (1 << z))

def lat2tile(lat, z):
    lat_rad = math.radians(lat)
    return int((1.0 - math.log(math.tan(lat_rad) + (1.0 / math.cos(lat_rad))) / math.pi) / 2.0 * (1 << z))

def tile2lon(x, z):
    return x / (1 << z) * 360.0 - 180.0

def tile2lat(y, z):
    n = math.pi - 2.0 * math.pi * y / (1 << z)
    return math.degrees(math.atan(math.sinh(n)))

def fetch_tile_with_retry(coord):
    z, x, y, cache_file = coord
    if os.path.exists(cache_file) and os.path.getsize(cache_file) > 1000:
        return x, y, cache_file

    url = f"https://server.arcgisonline.com/ArcGIS/rest/services/World_Shaded_Relief/MapServer/tile/{z}/{y}/{x}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BOOKINDEX HighRes Terrain Fetcher"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = resp.read()
                if len(data) > 500:
                    with open(cache_file, "wb") as f:
                        f.write(data)
                    return x, y, cache_file
        except Exception as e:
            if attempt == 3:
                print(f"  [!] 瓦片 ({z}, {x}, {y}) 下载失败: {e}")
            time.sleep(0.5 * (attempt + 1))
    return x, y, None

def build_terrain_basemap():
    x_min = lon2tile(FULL_LON_MIN, ZOOM)
    x_max = lon2tile(FULL_LON_MAX, ZOOM)
    y_min = lat2tile(FULL_LAT_MAX, ZOOM)  # 纬度越高 y 越小
    y_max = lat2tile(FULL_LAT_MIN, ZOOM)

    cols = x_max - x_min + 1
    rows = y_max - y_min + 1
    print(f"[*] 正在下载高清地形瓦片: Zoom={ZOOM}, X=[{x_min}..{x_max}] ({cols}列), Y=[{y_min}..{y_max}] ({rows}行), 共计 {cols * rows} 张瓦片")

    cache_dir = os.path.join(ROOT, "data", ".terrain_cache")
    os.makedirs(cache_dir, exist_ok=True)

    tasks = []
    for x in range(x_min, x_max + 1):
        for y in range(y_min, y_max + 1):
            c_file = os.path.join(cache_dir, f"{ZOOM}_{x}_{y}.png")
            tasks.append((ZOOM, x, y, c_file))

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(fetch_tile_with_retry, tasks))

    print(f"[*] 瓦片下载完毕，耗时 {time.time()-t0:.2f}s，正在拼接大图 ({cols*256} x {rows*256})...")

    mosaic = Image.new("RGB", (cols * 256, rows * 256), (220, 220, 220))
    for x, y, c_file in results:
        c_idx = x - x_min
        r_idx = y - y_min
        if c_file and os.path.exists(c_file):
            try:
                t_img = Image.open(c_file).convert("RGB")
                mosaic.paste(t_img, (c_idx * 256, r_idx * 256))
            except Exception:
                pass

    print("[*] 瓦片拼接完成，正在进行墨卡托 -> 等角矩形投影严格几何矫正...")

    # 计算拼接图的经纬度边界
    mosaic_lon_min = tile2lon(x_min, ZOOM)
    mosaic_lon_max = tile2lon(x_max + 1, ZOOM)
    mosaic_lat_max = tile2lat(y_min, ZOOM)
    mosaic_lat_min = tile2lat(y_max + 1, ZOOM)

    mosaic_w, mosaic_h = mosaic.size

    result = Image.new("RGB", (OUT_WIDTH, OUT_HEIGHT))

    # 建立每行 Y 对应的墨卡托源行号 source_y
    source_y_indices = []
    for out_y in range(OUT_HEIGHT):
        lat = FULL_LAT_MAX - (out_y / (OUT_HEIGHT - 1)) * (FULL_LAT_MAX - FULL_LAT_MIN)
        lat_rad = math.radians(lat)
        # Web Mercator y in tile coords (normalized 0..1 relative to mosaic)
        merc_y_norm = (1.0 - math.log(math.tan(lat_rad) + (1.0 / math.cos(lat_rad))) / math.pi) / 2.0 * (1 << ZOOM)
        src_y = (merc_y_norm - y_min) * 256.0
        src_y = max(0, min(mosaic_h - 1, int(round(src_y))))
        source_y_indices.append(src_y)

    # 经度裁剪范围
    src_x_start = int(round((FULL_LON_MIN - mosaic_lon_min) / (mosaic_lon_max - mosaic_lon_min) * mosaic_w))
    src_x_end = int(round((FULL_LON_MAX - mosaic_lon_min) / (mosaic_lon_max - mosaic_lon_min) * mosaic_w))

    crop_h_intermediate = mosaic.crop((src_x_start, 0, src_x_end, mosaic_h))
    crop_h_resized_w = crop_h_intermediate.resize((OUT_WIDTH, mosaic_h), Image.Resampling.BILINEAR)

    pixels_src = crop_h_resized_w.load()
    pixels_dst = result.load()

    for out_y, src_y in enumerate(source_y_indices):
        for out_x in range(OUT_WIDTH):
            pixels_dst[out_x, out_y] = pixels_src[out_x, src_y]

    print("[*] 几何重投影完成，正在进行古典水墨山川高清立体艺术调色（提升清晰度与对比度）...")

    gray = ImageOps.grayscale(result)
    # 动态范围拉伸：将瓦片原始灰度拉伸至 0..255 全动态范围，使山脉阴影深邃挺拔
    stretched_gray = ImageOps.autocontrast(gray, cutoff=0.5)

    enhancer_contrast = ImageEnhance.Contrast(stretched_gray)
    contrast_gray = enhancer_contrast.enhance(1.20)

    enhancer_sharp = ImageEnhance.Sharpness(contrast_gray)
    sharp_gray = enhancer_sharp.enhance(1.35)

    # 将 0~255 的地形阴影映射到深沉清雅的水墨山峦色阶：
    # 极暗部（0，深山峡谷背阴） -> 玄青水墨色 RGB(38, 48, 52)
    # 中山阴（128，缓坡丘陵）   -> 苍翠青黛灰 RGB(155, 165, 160)
    # 平原亮部（255，盆地华北中原平原） -> 纯正温润宣纸米白 RGB(250, 247, 240) = #FAF7F0
    lut = []
    for val in range(256):
        t = val / 255.0  # 0 为最深山影，1 为平原
        # S 型非线性对比曲线：平原更加宽阔明亮洁净，高山峡谷更加挺拔深邃
        t_curve = math.pow(t, 0.82)
        r = int(38 + (250 - 38) * t_curve)
        g = int(48 + (247 - 48) * t_curve)
        b = int(52 + (240 - 52) * t_curve)
        lut.extend([r, g, b])

    colored = sharp_gray.point(lut, mode="RGB")

    out_path = os.path.join(OUT_DIR, "terrain_basemap.jpg")
    colored.save(out_path, "JPEG", quality=92, optimize=True)
    size_kb = os.path.getsize(out_path) / 1024
    print(f"[✓] 高清立体山脉自然地形底图生成成功: {out_path} ({size_kb:.1f} KB, 分辨率: {OUT_WIDTH}x{OUT_HEIGHT})")

    if os.path.exists(DIST_DIR):
        dist_path = os.path.join(DIST_DIR, "terrain_basemap.jpg")
        colored.save(dist_path, "JPEG", quality=92, optimize=True)
        print(f"[✓] 同步至离线分发目录: {dist_path}")

if __name__ == "__main__":
    build_terrain_basemap()
