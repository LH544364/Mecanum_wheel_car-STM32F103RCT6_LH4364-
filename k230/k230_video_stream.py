# K230 无线图传服务端 - 双通道方案
# Ch0: YUV→LCD 硬件直连 (800x480)
# Ch1: RGB→JPEG→TCP 图传 (640x360)
# 优化: OSD 仅在信息变化时更新, JPEG 质量可调
import time, os, sys
import socket
import network
import image
import gc

from media.sensor import *
from media.display import *
from media.media import *

# ========== WiFi 配置 ==========
SSID = "LH_TX"
PASSWORD = "LH544364"
TCP_PORT = 8888

print("正在连接 WiFi: %s ..." % SSID)
sta = network.WLAN(network.STA_IF)
sta.disconnect()
time.sleep(1)
sta.connect(SSID, PASSWORD)

print("等待获取 IP", end="")
for _ in range(30):
    if sta.ifconfig()[0] != '0.0.0.0':
        break
    print(".", end="")
    time.sleep(0.5)
print()

if sta.ifconfig()[0] != '0.0.0.0':
    ip, mask, gw, dns = sta.ifconfig()
    print("========================================")
    print("  WiFi 连接成功！IP: %s" % ip)
    print("========================================")
else:
    ip = "0.0.0.0"
    print("WiFi 连接失败！")

# ========== 参数 ==========
LCD_W, LCD_H = 800, 480
STREAM_W, STREAM_H = 320, 240
JPEG_QUALITY = 30

sensor_obj = None
server_sock = None
client_sock = None
osd_img = None

last_status = ""
last_fps_time = time.time()
frame_count = 0
fps_show = 0
osd_needs_update = True

try:
    # ----- 初始化摄像头 -----
    print("初始化摄像头...")
    sensor_obj = Sensor()
    sensor_obj.reset()

    # Ch0: LCD 硬件直连 (YUV420SP → Display)
    sensor_obj.set_framesize(width=LCD_W, height=LCD_H, chn=CAM_CHN_ID_0)
    sensor_obj.set_pixformat(Sensor.YUV420SP, chn=CAM_CHN_ID_0)
    bind_info = sensor_obj.bind_info(x=0, y=0, chn=CAM_CHN_ID_0)
    Display.bind_layer(**bind_info, layer=Display.LAYER_VIDEO1)

    # Ch1: 图传抓帧 (RGB888 → JPEG)
    sensor_obj.set_framesize(width=STREAM_W, height=STREAM_H, chn=CAM_CHN_ID_1)
    sensor_obj.set_pixformat(Sensor.RGB888, chn=CAM_CHN_ID_1)

    # LCD 初始化，开 OSD 层显示状态
    Display.init(Display.ST7701, width=LCD_W, height=LCD_H, to_ide=True, osd_num=1)
    osd_img = image.Image(LCD_W, LCD_H, image.ARGB8888)

    sensor_obj.run()
    print("摄像头已启动")

    # ----- TCP 服务端 -----
    if ip != "0.0.0.0":
        addr = socket.getaddrinfo(ip, TCP_PORT)[0][-1]
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(addr)
        server_sock.listen(1)
        server_sock.settimeout(0)
        print("TCP 图传: %s:%d  分辨率: %dx%d" % (ip, TCP_PORT, STREAM_W, STREAM_H))
    else:
        print("WiFi 未连接，仅本地显示")

    # ========== 主循环 ==========
    while True:
        os.exitpoint()

        # --- 接受客户端 ---
        if server_sock:
            try:
                res = server_sock.accept()
                if res:
                    if client_sock:
                        try: client_sock.close()
                        except: pass
                    client_sock = res[0]
                    print("客户端连接: %s" % str(res[1]))
                    client_sock.settimeout(0)
                    osd_needs_update = True
            except Exception as e:
                if hasattr(e, 'errno') and e.errno != 11:
                    pass

        # --- 抓帧 + 发送 ---
        if client_sock:
            try:
                img = sensor_obj.snapshot(chn=CAM_CHN_ID_1)
                jpeg = img.compress(quality=JPEG_QUALITY)
                jpeg_bytes = jpeg.to_bytes() if hasattr(jpeg, 'to_bytes') else bytes(jpeg)

                if jpeg_bytes and len(jpeg_bytes) > 0:
                    header = len(jpeg_bytes).to_bytes(4, 'big')
                    try:
                        client_sock.send(header + jpeg_bytes)
                        frame_count += 1
                    except:
                        print("客户端断开")
                        try: client_sock.close()
                        except: pass
                        client_sock = None
                        osd_needs_update = True
            except Exception as e:
                if hasattr(e, 'errno') and e.errno != 11:
                    pass

        # --- FPS 计算 ---
        now = time.time()
        if now - last_fps_time >= 1.0:
            fps_show = frame_count
            frame_count = 0
            last_fps_time = now
            osd_needs_update = True

        # --- OSD 刷新 (仅在需要时，避免每帧渲染) ---
        if osd_needs_update and osd_img:
            osd_needs_update = False
            osd_img.clear()

            # 顶部状态栏 (用 fill_rectangle 替代逐像素循环)
            osd_img.draw_rectangle(0, 0, LCD_W, 48, color=(160, 0, 0, 0), fill=True)

            # 状态文字
            status = "FPS:%d | %dx%d | JPEG Q:%d" % (fps_show, STREAM_W, STREAM_H, JPEG_QUALITY)
            osd_img.draw_string_advanced(8, 6, 22, status, color=(255, 0, 255, 0))

            ip_info = "rtsp://%s:%d" % (ip, TCP_PORT) if ip != "0.0.0.0" else "No WiFi"
            osd_img.draw_string_advanced(8, 30, 16, ip_info, color=(255, 200, 200, 200))

            # 客户端状态
            if client_sock:
                osd_img.draw_string_advanced(650, 6, 18, "CONN", color=(255, 0, 255, 0))
            else:
                osd_img.draw_string_advanced(650, 6, 18, "WAIT", color=(255, 255, 100, 100))

            Display.show_image(osd_img, 0, 0, Display.LAYER_OSD1)

        # 周期刷新 OSD（保证 FPS 数字更新）
        if frame_count % 5 == 0:
            osd_needs_update = True

except KeyboardInterrupt as e:
    print("用户停止")
except BaseException as e:
    sys.print_exception(e)
finally:
    if client_sock:
        try: client_sock.close()
        except: pass
    if server_sock:
        try: server_sock.close()
        except: pass
    if isinstance(sensor_obj, Sensor):
        sensor_obj.stop()
    Display.deinit()
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)
    print("退出。")
