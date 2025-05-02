import paho.mqtt.client as mqtt
import stmpy
import logging
import json
from appJar import gui
import time

MQTT_BROKER = 'mqtt20.iik.ntnu.no'
MQTT_PORT = 1883

MQTT_TOPIC_INPUT = 'team02Input'
MQTT_TOPIC_OUTPUT = 'team02Output'


def get_location():
    return (6.5, 10)


class PhoneLogic:
    def __init__(self, name, func, component):
        self._logger = logging.getLogger(__name__)
        self.name = name
        self.func = func
        self.component = component
        self.stm = None
        self.destination = (None, None)
        self.app = component.app
        self.start_time = time.time()
        self.price = 0
        self.selected_escooter = ""

    def clear_gui(self):
        self.app.removeAllWidgets()
        self.app.startLabelFrame("Escooter APP")
        self.app.stopLabelFrame()

    def start_trip(self):
        def gui_start():
            self.clear_gui()
            self.app.addLabel("label_intro", "Welcome! Send your location to find scooters.")
            self.app.addButton("Send Location", self.send_location)

        self.app.queueFunction(gui_start)

    def send_location(self):
        # Simulate user location and notify server
        msg = {"command": "phone_location", "location": get_location(), "phone_name": self.name}
        self.component.publish_message(msg)
        self.stm.send("phone_location_exchanged")

    def escooters_gui_select_escooter(self, escooters, distance):
        def gui_escooters():
            self.clear_gui()
            self.app.addLabel("label_escooters", "Select an available scooter:")
            for i in range(len(escooters)):
                self.app.addButton(f"Select {escooters[i]['id']} (Distance {distance[i]}m)",
                                   lambda btn, s=escooters[i]['id']: self.select_escooter(s))

        self.app.queueFunction(gui_escooters)
        self.app.queueFunction(gui_escooters)

    def select_escooter(self, scooter_id):
        self.component.publish_message(
            {"command": "selected_escooter", "escooter": scooter_id, "phone_name": self.name})
        self.selected_escooter = scooter_id
        self.stm.send("send_escooter")

        def gui_destination():
            self.clear_gui()
            self.app.addLabel("label_dest", "Click to send your destination:")
            self.app.addButton("Send Destination", self.send_destination)

        self.app.queueFunction(gui_destination)

    def send_destination(self):
        self.destination = (63.45, 10.38)
        self.component.publish_message(
            {"command": "exchange_destination", "location": get_location(), "destination": self.destination,
             "phone_name": self.name})
        self.stm.send("send_destination")


    def receive_route_suggestion(self, distance, price):
        def gui_suggestion():
            self.clear_gui()
            self.app.addLabel("distance_label", f"Distance to destination: {distance} meters")
            self.app.addLabel("price_label", f"Estimated price: {price} NOK")
            self.app.addButton("Confirm Route", self.confirm_route)
            self.app.addButton("Decline Route", self.decline_route)
            self.price = price
        self.app.queueFunction(gui_suggestion)

    def confirm_route(self):
        self.component.publish_message({"command": "route_confirmed", "confirm": True, "phone_name": self.name,
                                        "Price": self.price})
        self.stm.send("route_confirmed")

        self.traveling_gui()

    def decline_route(self):
        self.component.publish_message({"command": "route_confirmed", "confirm": False, "phone_name": self.name})
        self.stm.send("route_not_confirmed")

        def gui_destination_again():
            self.clear_gui()
            self.app.addLabel("label_dest", "Destination rejected, choose again:")
            self.app.addButton("Send Destination", self.send_destination)

        self.app.queueFunction(gui_destination_again)

    def traveling_gui(self):
        def gui_traveling():
            self.clear_gui()
            self.app.addLabel("travel_label", "Traveling... You can:")
            self.app.addButton("Ask for Price", self.ask_price)
            self.app.addButton("Ask for Distance Update", self.ask_distance)
            self.app.addLabel("distance_label", "")
            self.app.addLabel("price_label", "")

        self.app.queueFunction(gui_traveling)
        self.check_arrival()

    def ask_price(self):
        self.component.publish_message({"command": "ask_price", "location": get_location(), "phone_name": self.name})

    def ask_distance(self):
        self.component.publish_message({"command": "ask_distance", "location": get_location(), "phone_name": self.name})

    def check_arrival(self):
        # Start checking arrival every second
        self.start_time = time.time()
        self._check_arrival_periodically()

    def _check_arrival_periodically(self):
        # Get the current location
        current_location = get_location()
        # Check the time elapsed since the start
        elapsed_time = time.time() - self.start_time

        # If the destination is reached or 20 seconds have passed, stop
        if current_location == self.destination or elapsed_time >= 10:
            self.component.publish_message({"command": "destination_reached",
                                            "escooter": self.selected_escooter,
                                            "phone_name": self.name})
            self.show_destination_reached_animation()
            print("FINISHED")
            return

        # If 20 seconds haven't passed yet, recheck in 1 second
        self.app.after(1000, self._check_arrival_periodically)

    def show_destination_reached_animation(self):
        # Define an animation for destination reached
        self.clear_gui()

        def animation_step(step=0):
            if step == 0:
                self.app.addLabel("destination_label", "Destination Reached!")
                self.app.setBackground("lightgreen")  # Change background to light green
            elif step == 1:
                self.app.setLabel("destination_label", "Destination Reached! 🎉")
                self.app.setBackground("lightblue")  # Change background to light blue
            elif step == 2:
                self.app.setLabel("destination_label", "Destination Reached! 🎉 🚗")
                self.app.setBackground("lightyellow")  # Change background to yellow

            # After the last animation step, close the window
            if step == 2:
                self.app.after(1000, self.app.stop)  # Close after 1 second

        # Run the animation steps with a delay
        self.app.after(1000, animation_step, 0)
        self.app.after(2000, animation_step, 1)
        self.app.after(3000, animation_step, 2)
        self.stm.send("destination_reached")


class PhoneSenderComponent:
    def __init__(self):
        self._logger = logging.getLogger(__name__)
        logging.basicConfig(level=logging.DEBUG)
        self._logger.info('Starting Component')

        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message
        self.mqtt_client.connect(MQTT_BROKER, MQTT_PORT)
        self.mqtt_client.loop_start()

        self.app = gui("Phone GUI")
        self.setup_gui()

        self.phone_logic = PhoneLogic("phone", None, self)
        self.phone_stm = self.phone_logic.create_machine(self.phone_logic.name, None, self)
        self.driver = stmpy.Driver()
        self.driver.add_machine(self.phone_stm)
        self.driver.start()

    def setup_gui(self):
        self.app.startLabelFrame("Escooter APP")
        self.app.stopLabelFrame()

    def start(self):
        self.app.go()

    def publish_message(self, msg):
        payload = json.dumps(msg)
        self.mqtt_client.publish(MQTT_TOPIC_INPUT, payload=payload, qos=2)

    def on_connect(self, client, userdata, flags, rc):
        self._logger.info('Connected to MQTT Broker')
        client.subscribe(MQTT_TOPIC_OUTPUT)

    def on_message(self, client, userdata, msg):
        data = json.loads(msg.payload.decode('utf-8'))
        self._logger.info(f"Received: {data}")

        msg_command = data.get("command")

        if msg_command == "escooters_list":
            scooters = data.get("escooters", [])
            distance = data.get("distance", [])
            self.phone_logic.escooters_gui_select_escooter(scooters, distance)
            self.phone_logic.stm.send("receive_escooters")

        elif msg_command == "suggest_route":
            distance = data.get("distance")
            price = data.get("price")
            self.phone_logic.receive_route_suggestion(distance, price)

        elif msg_command == "distance_remaining":
            distance = data.get("distance")

            self.app.setLabel("distance_label", f"Distance to destination: {distance} meters")

        elif msg_command == "price_remaining":
            price = data.get("price")
            self.app.setLabel("price_label", f"Estimated price: {price} NOK")

        else:
            print(f"Command ignored: {msg_command}")

def create_machine(self, phone_name, func, component):
    t0 = {"source": "initial", "target": "AwaitUserLocation", "effect": "start_trip()"}
    t1 = {"trigger": "phone_location_exchanged", "source": "AwaitUserLocation", "target": "AwaitServerInfo"}
    t2 = {"trigger": "receive_escooters", "source": "AwaitServerInfo", "target": "SelectEscooter"}
    t3 = {"trigger": "send_escooter", "source": "SelectEscooter", "target": "SelectDestination"}
    t4 = {"trigger": "send_destination", "source": "SelectDestination", "target": "ConfirmRoute"}
    t5 = {"trigger": "route_confirmed", "source": "ConfirmRoute", "target": "TravelingAndCheckRouteInfo"}
    t6 = {"trigger": "route_not_confirmed", "source": "ConfirmRoute", "target": "SelectDestination"}
    t7 = {"trigger": "ask_price", "source": "TravelingAndCheckRouteInfo", "target": "PriceAsked"}
    t8 = {"trigger": "ask_route", "source": "TravelingAndCheckRouteInfo", "target": "DistanceAsked"}
    t9 = {"trigger": "received_distance", "source": "DistanceAsked", "target": "TravelingAndCheckRouteInfo"}
    t10 = {"trigger": "received_price", "source": "PriceAsked", "target": "TravelingAndCheckRouteInfo"}
    t11 = {"trigger": "destination_reached", "source": "TravelingAndCheckRouteInfo", "target": "final"}

    phone_stm = stmpy.Machine(name=phone_name, transitions=[t0, t1, t2, t3, t4, t5, t6, t7, t8, t9, t10, t11], obj=self)
    self.stm = phone_stm
    return phone_stm


PhoneLogic.create_machine = create_machine

if __name__ == '__main__':
    phone_component = PhoneSenderComponent()
    phone_component.start()

"""
from sense_hat import SenseHat
import time
import numpy as np

sense = SenseHat()

def detect_movement(threshold=0.1):
    prev_accel = np.array([0, 0, 0])

    while True:
        # Get acceleration data
        accel = sense.get_accelerometer_raw()
        accel_vector = np.array([accel['x'], accel['y'], accel['z']])

        # Compute the difference from previous reading
        diff = np.linalg.norm(accel_vector - prev_accel)

        if diff > threshold:
            print("Movement detected!")
        else:
            print("No movement.")

        prev_accel = accel_vector
        time.sleep(0.5)

# Run the motion detection function
detect_movement()
"""
