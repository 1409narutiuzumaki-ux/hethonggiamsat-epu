from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO
import threading
import time
import datetime
import webbrowser
import random
import os
import pandas as pd
from openpyxl.styles import Font, Alignment

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

is_simulating = False
simulation_thread = None

# Cấu hình độc lập cho từng phòng
ROOM_CONFIGS = {
    "r1": {
        "name": "Phòng Học Lớn", 
        "base_safe": 15.0, "base_warn": 40.0, "base_danger": 55.0, 
        "thresh_warn": 35.0, "thresh_danger": 50.0
    },
    "r2": {
        "name": "Phòng Học Nhỏ", 
        "base_safe": 10.0, "base_warn": 28.0, "base_danger": 45.0, 
        "thresh_warn": 25.0, "thresh_danger": 40.0
    },
    "r3": {
        "name": "Phòng Bảo Vệ",  
        "base_safe": 5.0,  "base_warn": 18.0, "base_danger": 28.0, 
        "thresh_warn": 15.0, "thresh_danger": 25.0
    }
}

def init_history():
    return {
        "total_runtime": 0,
        "rooms": {
            "r1": {"safe": 0, "warn": 0, "danger": 0, "last": "Safe"},
            "r2": {"safe": 0, "warn": 0, "danger": 0, "last": "Safe"},
            "r3": {"safe": 0, "warn": 0, "danger": 0, "last": "Safe"}
        },
        "event_log": []
    }

history_stats = init_history()

SAMPLE_EXCEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kich_ban_1_pha_chuan.xlsx")

def create_clean_sample_excel():
    start_time = datetime.datetime(2026, 10, 15, 8, 0, 0)
    data = []
    random.seed(42)
    for i in range(180):
        t = start_time + datetime.timedelta(seconds=i)
        t_str = t.strftime("%d/%m/%Y %H:%M:%S")
        phase_in_cycle = i % 45
        if phase_in_cycle < 15: base_i = 10.0
        elif phase_in_cycle < 30: base_i = 28.0
        else: base_i = 45.0
        i_val = round(base_i + random.uniform(-0.2, 0.2), 1)
        u_val = round(225.0 - (base_i * 0.3) + random.uniform(-0.3, 0.3), 1)
        data.append([t_str, u_val, i_val])
    df = pd.DataFrame(data, columns=["Thời gian", "Điện áp (V)", "Dòng điện (A)"])
    with pd.ExcelWriter(SAMPLE_EXCEL_PATH, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name="DuLieuDo")
        ws = writer.sheets["DuLieuDo"]
        ws.column_dimensions['A'].width = 25
        ws.column_dimensions['B'].width = 18
        ws.column_dimensions['C'].width = 18
        header_font = Font(name='Times New Roman', size=12, bold=True)
        cell_font = Font(name='Times New Roman', size=12)
        center_align = Alignment(horizontal='center', vertical='center')
        for cell in ws[1]:
            cell.font = header_font
            cell.alignment = center_align
        for row in ws.iter_rows(min_row=2, max_row=len(df) + 1):
            row[0].number_format = '@'
            for cell in row:
                cell.font = cell_font
                cell.alignment = center_align

def run_simulation():
    global is_simulating, history_stats
    start_time = time.time()
    base_scenario_idx = 0
    
    while is_simulating:
        current_time = time.time()
        
        if current_time - start_time >= 5.0:
            base_scenario_idx = (base_scenario_idx + 1) % 3
            start_time = current_time
            
        history_stats["total_runtime"] += 1
        rooms_data = {}
        
        for i, r_key in enumerate(["r1", "r2", "r3"]):
            cfg = ROOM_CONFIGS[r_key]
            r_scenario = (base_scenario_idx + i) % 3
            
            if r_scenario == 0: base_current = cfg["base_safe"]
            elif r_scenario == 1: base_current = cfg["base_warn"]
            else: base_current = cfg["base_danger"]
            
            c_val = round(base_current + random.uniform(-0.2, 0.2), 2)
            v_val = round(225.0 - (c_val * 0.3) + random.uniform(-0.5, 0.5), 1)
            
            status = "Safe"
            advice = "Bình thường. Thông số an toàn."
            if c_val > cfg["thresh_danger"]:
                status = "Danger"
                advice = f"NGUY HIỂM: Ngắt aptomat ngay! (Ngưỡng {cfg['thresh_danger']}A)"
            elif c_val > cfg["thresh_warn"]:
                status = "Warning"
                advice = f"CẢNH BÁO: Tắt bớt thiết bị. (Ngưỡng {cfg['thresh_warn']}A)"
                
            rooms_data[r_key] = {
                "current": c_val, "voltage": v_val, "status": status, "advice": advice
            }
            
            if status == "Safe": history_stats["rooms"][r_key]["safe"] += 1
            elif status == "Warning": history_stats["rooms"][r_key]["warn"] += 1
            elif status == "Danger": history_stats["rooms"][r_key]["danger"] += 1
            
            last = history_stats["rooms"][r_key]["last"]
            if status != last:
                ts = time.strftime("%d/%m/%Y %H:%M:%S")
                r_name = cfg["name"]
                if status == "Warning":
                    history_stats["event_log"].append(f"[{ts}] {r_name}: Cảnh báo quá tải ({c_val}A)")
                elif status == "Danger":
                    history_stats["event_log"].append(f"[{ts}] {r_name}: NGUY HIỂM CHÁY NỔ ({c_val}A)")
                elif status == "Safe" and last != "Safe":
                    history_stats["event_log"].append(f"[{ts}] {r_name}: Đã an toàn trở lại.")
            history_stats["rooms"][r_key]["last"] = status
            
        latest_data = {
            "timestamp": time.strftime("%H:%M:%S"),
            "r1": rooms_data["r1"],
            "r2": rooms_data["r2"],
            "r3": rooms_data["r3"]
        }
        socketio.emit('new_sensor_data', latest_data)
        time.sleep(1.0)

@app.route('/toggle_simulation', methods=['POST'])
def toggle_simulation():
    global is_simulating, simulation_thread, history_stats
    data = request.json
    action = data.get('action')
    if action == 'start':
        if not is_simulating:
            history_stats = init_history()
            is_simulating = True
            simulation_thread = threading.Thread(target=run_simulation)
            simulation_thread.daemon = True
            simulation_thread.start()
            return jsonify({"message": "Đã khởi động máy đo 3 phòng."})
    elif action == 'stop':
        is_simulating = False
        return jsonify({"message": "Đã dừng hệ thống."})
    return jsonify({"error": "Hành động không hợp lệ"}), 400

@app.route('/get_report', methods=['GET'])
def get_report():
    return jsonify(history_stats)

@app.route('/download_sample', methods=['GET'])
def download_sample():
    if not os.path.exists(SAMPLE_EXCEL_PATH):
        create_clean_sample_excel()
    return send_file(SAMPLE_EXCEL_PATH, as_attachment=True, download_name="kich_ban_1_pha_chuan.xlsx")

@app.route('/internal')
def internal_mode():
    return render_template('internal.html')

@app.route('/analyze_1phase', methods=['POST'])
def analyze_1phase():
    thresh_warn = 25.0
    thresh_danger = 40.0
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "Không có file"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "Chưa chọn file"}), 400
    try:
        if file.filename.endswith('.csv'):
            try: df = pd.read_csv(file, encoding='utf-8-sig')
            except Exception:
                file.seek(0)
                df = pd.read_csv(file, encoding='latin1')
        else:
            df = pd.read_excel(file)
            
        if len(df.columns) < 3:
            return jsonify({"success": False, "error": "File phải có đủ 3 cột: Thời gian, Điện áp (V), Dòng điện (A)"}), 400
            
        col_time = df.columns[0]; col_u = df.columns[1]; col_i = df.columns[2]
        df = df.dropna(subset=[col_time, col_u, col_i])
            
        warning_count = 0; danger_count = 0; safe_count = 0
        total_runtime = len(df); event_log = []; last_status = "Safe"
        
        for index, row in df.iterrows():
            t_str = str(row[col_time]).strip()
            u_val = float(row[col_u])
            i_val = float(row[col_i])
            
            if i_val > thresh_danger: status = "Danger"
            elif i_val > thresh_warn: status = "Warning"
            else: status = "Safe"
                
            if status == "Safe": safe_count += 1
            if status != last_status:
                if status == "Warning":
                    warning_count += 1
                    event_log.append(f"[{t_str}] Cảnh báo: Dòng điện tăng lên {i_val:.1f}A")
                elif status == "Danger":
                    danger_count += 1
                    event_log.append(f"[{t_str}] Nguy hiểm: Quá tải nghiêm trọng ở mức {i_val:.1f}A")
                elif status == "Safe" and last_status != "Safe":
                    event_log.append(f"[{t_str}] Hệ thống đã an toàn trở lại.")
            last_status = status
            
        data = {
            "success": True, "labels": df[col_time].astype(str).tolist(),
            "U_val": df[col_u].astype(float).tolist(), "I_val": df[col_i].astype(float).tolist(),
            "report_data": {
                "total_runtime": total_runtime, "safe_count": safe_count,
                "warning_count": warning_count, "danger_count": danger_count, "event_log": event_log
            }
        }
        return jsonify(data)
    except Exception as e:
        return jsonify({"success": False, "error": f"Lỗi đọc dữ liệu: {str(e)}"}), 500

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    create_clean_sample_excel()
    # Nhận Port động từ nền tảng Cloud (Render/Koyeb), nếu không có thì chạy cổng 5000 ở Local
    port = int(os.environ.get("PORT", 5000))
    # Tắt chế độ debug và xóa dòng bật trình duyệt tự động
    socketio.run(app, debug=False, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)