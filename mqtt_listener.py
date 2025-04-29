import paho.mqtt.client as mqtt

# Configuration from your setup
MQTT_BROKER = 'mqtt20.iik.ntnu.no'
MQTT_PORT = 1883
MQTT_TOPIC = '#'  # Subscribe to all topics (use 'team02Output' or similar to filter)

def on_connect(client, userdata, flags, rc):
    print(f"[+] Connected to {MQTT_BROKER}:{MQTT_PORT} with result code {rc}")
    client.subscribe(MQTT_TOPIC)
    print(f"[+] Subscribed to topic: {MQTT_TOPIC}")

def on_message(client, userdata, msg):
    print(f"[{msg.topic}] {msg.payload.decode('utf-8')}")

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

print(f"[*] Connecting to {MQTT_BROKER}:{MQTT_PORT} ...")
client.connect(MQTT_BROKER, MQTT_PORT, 60)
client.loop_forever()
