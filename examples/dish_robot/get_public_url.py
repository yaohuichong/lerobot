import subprocess
import json
import urllib.request
import time

def get_ngrok_url():
    try:
        with urllib.request.urlopen("http://localhost:4040/api/tunnels") as response:
            data = json.loads(response.read().decode())
            if data.get("tunnels"):
                return data["tunnels"][0]["public_url"]
    except Exception as e:
        print(f"获取ngrok URL失败: {e}")
    return None

def generate_qrcode(url: str, output_path: str = "dish_robot_qr.png"):
    try:
        import qrcode
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(output_path)
        print(f"[OK] 二维码已保存: {output_path}")
        return True
    except ImportError:
        print("[WARN] qrcode未安装，跳过二维码生成")
        print("安装: pip install qrcode[pil]")
        return False

def main():
    print("=" * 50)
    print("获取ngrok公网地址...")
    print("=" * 50)
    
    url = get_ngrok_url()
    
    if url:
        print(f"\n公网访问地址: {url}")
        print(f"\n内网访问地址: http://192.168.0.16:7860")
        print(f"Tailscale地址: http://100.72.90.23:7860")
        print("=" * 50)
        
        generate_qrcode(url)
        
        print("\n扫码或直接访问上述地址即可使用打饭机器人！")
        print("\n注意: ngrok免费版首次访问会显示警告页面，点击'Visit Site'即可")
    else:
        print("[ERROR] 无法获取ngrok URL，请确保ngrok正在运行")
        print("启动命令: sudo systemctl start ngrok")

if __name__ == "__main__":
    main()
