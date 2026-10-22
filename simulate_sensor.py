import paho.mqtt.client as mqtt
import json
import time
import random

MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC = "EPU/KTD/QTDien"

client = mqtt.Client()
client.connect(MQTT_BROKER, MQTT_PORT, 60)

# Mô phỏng sụt áp tỷ lệ thuận với dòng điện
def calculate_voltage(current):
    base_voltage = 225.0
    # Dòng càng cao, sụt áp càng lớn (giả lập R đường dây)
    drop = current * 0.4 
    voltage = base_voltage - drop + random.uniform(-1.5, 1.5)
    return round(voltage, 1)

def send_scenario(scenario_name, min_curr, max_curr, duration_secs):
    print(f"\n--- Kịch bản: {scenario_name} ---")
    for _ in range(duration_secs):
        current = round(random.uniform(min_curr, max_curr), 2)
        voltage = calculate_voltage(current)
        
        payload = {"voltage": voltage, "current": current}
        client.publish(MQTT_TOPIC, json.dumps(payload))
        print(f"Đã phát: U={voltage}V, I={current}A")
        time.sleep(1.5)

while True:
    send_scenario("An Toàn (Phòng học chỉ bật quạt, đèn)", 5.0, 12.0, 8)
    send_scenario("Cảnh Báo (Bật thêm dãy điều hòa)", 26.0, 32.0, 8)
    send_scenario("Nguy Hiểm (Khởi động đồng loạt dàn máy tính + điều hòa)", 42.0, 50.0, 8)