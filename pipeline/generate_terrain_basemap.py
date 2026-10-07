# -*- coding: utf-8 -*-
"""
生成中国两汉三国核心区域真实自然地形底图（Shaded Relief Basemap）
数据源：ESRI World Shaded Relief（全球权威山阴立体晕渲高程服务，纯自然山川地貌，无现代公路行政界线干扰）
范围：经度 104.0°E ~ 120.5°E，纬度 27.8°N ~ 37.2°N
投影转换：Web 墨卡托 (EPSG:3857) -> 等角矩形投影 (Plate Carrée)
色调调整：典雅古典宣纸色调（纸白 #FAF7F0 + 青灰色水墨山峦立体光影）
输出：
  - app/web/terrain_basemap.jpg
  - dist/terrain_basemap.jpg
"""
import math
import os
import sys
import urllib.request
from PIL import Image, ImageEnhance, ImageOps

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "app", "web")
DIST_DIR = os.path.join(ROOT, "dist")

LON_MIN = 104.0
LON_MAX = 120.5
LAT_MIN = 27.8
LAT_MAX = 37.2

OUT_WIDTH = 2000
OUT_HEIGHT = 1240  # 对应 1000x620 的 2x 超清 retina 比例

ZOOM = 7

def lon2tile(lon, z):
    return int((lon + 180.0) / 360.0 * (1 << z))

def lat2tile(lat, z):
    lat_rad = math.radians(lat)
    return int((1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2.0 * (1 << z))

def tile2lon(x, z):
    return x / (1 << z) * 360.0 - 180.0

def tile2lat(y, z):
    n = math.pi - 2.0 * math.pi * y / (1 << z)
    return math.degrees(math.atan(math.sinh(n)))

def fetch_tile(z, x, y):
    url = f"https://server.arcgisonline.com/ArcGIS/rest/services/World_Shaded_Relief/MapServer/tile/{z}/{y}/{x}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 BOOKINDEX Terrain Fetcher"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read()

def build_terrain_basemap():
    x_min = lon2tile(LON_MIN, ZOOM)
    x_max = lon2tile(LON_MAX, ZOOM)
    y_min = lat2tile(LAT_MAX, ZOOM)  # 纬度越高 y 越小
    y_max = lat2tile(LAT_MIN, ZOOM)

    print(f"[*] 正在下载地形瓦片: Zoom={ZOOM}, X=[{x_min}..{x_max}], Y=[{y_min}..{y_max}]")
    cols = x_max - x_min + 1
    rows = y_max - y_min + 1
    print(f"[*] 瓦片网格: {cols} 列 x {rows} 行, 共计 {cols * rows} 张瓦片")

    cache_dir = os.path.join(ROOT, ".tmp_terrain_cache")
    os.makedirs(cache_dir, exist_ok=True)

    mosaic = Image.new("RGB", (cols * 256, rows * 256))

    for c_idx, x in enumerate(range(x_min, x_max + 1)):
        for r_idx, y in enumerate(range(y_min, y_max + 1)):
            cache_file = os.path.join(cache_dir, f"{ZOOM}_{x}_{y}.png")
            if not os.path.exists(cache_file):
                try:
                    data = fetch_tile(ZOOM, x, y)
                    with open(cache_file, "wb") as f:
                        f.write(data)
                except Exception as e:
                    print(f"  [!] 瓦片 ({ZOOM}, {x}, {y}) 获取失败: {e}")
                    # 用中性灰色填充
                    tile_img = Image.new("RGB", (256, 256), (220, 220, 220))
                    mosaic.paste(tile_img, (c_idx * 256, r_idx * 256))
                    continue
            tile_img = Image.open(cache_file).convert("RGB")
            mosaic.paste(tile_img, (c_idx * 256, r_idx * 256))

    print("[*] 瓦片拼接完成，正在进行墨卡托 -> 等角矩形投影几何矫正...")

    # 计算拼接图的经纬度边界
    mosaic_lon_min = tile2lon(x_min, ZOOM)
    mosaic_lon_max = tile2lon(x_max + 1, ZOOM)
    mosaic_lat_max = tile2lat(y_min, ZOOM)
    mosaic_lat_min = tile2lat(y_max + 1, ZOOM)

    mosaic_w, mosaic_h = mosaic.size

    # 重投影：对目标等角矩形画布上的每个像元进行坐标反算映射
    # 等角投影下：X 线性映射到 lon，Y 线性映射到 lat
    # 瓦片图为 Web 墨卡托：X 同样线性映射到 lon，Y 则为 ln(tan(pi/4 + lat/2))
    result = Image.new("RGB", (OUT_WIDTH, OUT_HEIGHT))
    
    # 利用矩阵逐行快速重采样
    # 因为经度方向在两个投影中均为线性映射，只有纬度方向需要墨卡托矫正！
    # 建立每行 Y 对应的墨卡托源行号 source_y
    source_y_indices = []
    for out_y in range(OUT_HEIGHT):
        lat = LAT_MAX - (out_y / (OUT_HEIGHT - 1)) * (LAT_MAX - LAT_MIN)
        lat_rad = math.radians(lat)
        # Web Mercator y in tile coords (normalized 0..1 relative to mosaic)
        merc_y_norm = (1.0 - math.log(math.tan(lat_rad) + (1.0 / math.cos(lat_rad))) / math.pi) / 2.0 * (1 << ZOOM)
        src_y = (merc_y_norm - y_min) * 256.0
        src_y = max(0, min(mosaic_h - 1, int(round(src_y))))
        source_y_indices.append(src_y)

    # 经度裁剪范围
    src_x_start = int(round((LON_MIN - mosaic_lon_min) / (mosaic_lon_max - mosaic_lon_min) * mosaic_w))
    src_x_end = int(round((LON_MAX - mosaic_lon_min) / (mosaic_lon_max - mosaic_lon_min) * mosaic_w))
    src_w = src_x_end - src_x_start

    crop_h_intermediate = mosaic.crop((src_x_start, 0, src_x_end, mosaic_h))
    crop_h_resized_w = crop_h_intermediate.resize((OUT_WIDTH, mosaic_h), Image.Resampling.BILINEAR)

    # 垂直方向按墨卡托矫正重采样生成等角投影
    pixels_src = crop_h_resized_w.load()
    pixels_dst = result.load()

    for out_y, src_y in enumerate(source_y_indices):
        for out_x in range(OUT_WIDTH):
            pixels_dst[out_x, out_y] = pixels_src[out_x, src_y]

    print("[*] 几何重投影完成，正在进行古典宣纸与青墨山峦艺术调色...")
    # 调色：转灰度 -> 提高山脉阴影对比度 -> 映射为古典宣纸底色 (#FAF7F0) 与山水墨青色 (#4D5859)
    gray = ImageOps.grayscale(result)
    # 对比度微调
    enhancer = ImageEnhance.Contrast(gray)
    contrast_gray = enhancer.enhance(1.35)

    # 将 0~255 的地形阴影映射到古风水墨调宣纸色：
    # 极亮部（255，平原/盆地） -> 纯宣纸米白 RGB(250, 247, 240) = #FAF7F0
    # 极暗部（0，巍峨山脉背阴/峡谷） -> 水墨青灰黛色 RGB(85, 95, 98)
    lut = []
    for val in range(256):
        t = val / 255.0  # 0 为最深山影，1 为最平平原
        # 保持高光平原干净明亮，山峰清晰挺拔
        t_curve = math.pow(t, 0.85)
        r = int(90 + (250 - 90) * t_curve)
        g = int(98 + (247 - 98) * t_curve)
        b = int(102 + (240 - 102) * t_curve)
        lut.extend([r, g, b])

    colored = contrast_gray.point(lut, mode="RGB")

    # 保存目标文件
    out_path = os.path.join(OUT_DIR, "terrain_basemap.jpg")
    colored.save(out_path, "JPEG", quality=88, optimize=True)
    size_kb = os.path.getsize(out_path) / 1024
    print(f"[✓] 真实山脉自然地形底图生成成功: {out_path} ({size_kb:.1f} KB)")

    # 同步到 dist
    if os.path.exists(DIST_DIR):
        dist_path = os.path.join(DIST_DIR, "terrain_basemap.jpg")
        colored.save(dist_path, "JPEG", quality=88, optimize=True)
        print(f"[✓] 同步至离线分发目录: {dist_path}")

    # 清理瓦片缓存
    try:
        import shutil
        shutil.rmtree(cache_dir, ignore_errors=True)
    except Exception:
        pass

if __name__ == "__main__":
    build_terrain_basemap()
