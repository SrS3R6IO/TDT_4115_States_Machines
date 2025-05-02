import paho.mqtt.client as mqtt
import stmpy
import logging
import json
import random

MQTT_BROKER = 'mqtt20.iik.ntnu.no'
MQTT_PORT = 1883

MQTT_TOPIC_INPUT = 'team02Input'
MQTT_TOPIC_OUTPUT = 'team02Output'


class ScooterLogic:
    def __init__(self, name, func, component):
        self._logger = logging.getLogger(__name__)
        self.name = name
        self.func = func
        self.component = component

    def get_location(self):
        return (random.randint(0, 100), random.randint(0, 100))

    def create_machine(self, scooter_name, func, component):

        # initial transition
        scooter_logic = ScooterLogic(name=scooter_name, func=func, component=component)
        t0 = {
            "source": "initial",
            "target": "AwaitServerRequest"
        }

        # await_server_request -> await_route_details
        t1 = {
            "trigger": "server_location_request",
            "source": "AwaitServerRequest",
            "target": "AwaitRouteDetails"
        }

        # t2 (if/else) -> arrived(finished)
        t2 = {
            "trigger": "received_route_details",
            "source": "AwaitRouteDetails",
            "target": "Traveling",
        }

        # t2 (if/else) -> await_server_request(not arrived yet)
        t3 = {
            "trigger": "arrived",
            "source": "Traveling",
            "target": "final",

        }

        t4 = {
            "trigger": "t",
            "source": "AwaiteRouteDetails",
            "target": "AwaitServerRequest",
            "effect": "started"
        }
        scooter_stm = stmpy.Machine(name=scooter_name, transitions=[t0, t1, t2, t3, t4],
                                    obj=scooter_logic)
        scooter_logic.stm = scooter_stm
        return scooter_stm

    def started(self):
        self.stm.start_timer('t', 2000)
    def receive_server_request(self, destination, price):
        print(destination, price)
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
        # Maybe display in the RaspberryPi a image with the info

    def provide_location(self, server_name, phone_location):
        location = self.get_location()
        msg = {"command": "receive_escooter_location", "location": location, "escooter_id": self.name,
               "busy": random.randint(0, 1),
               "server_name": server_name, "phone_location": phone_location
               }
        self.component.publish_message(msg)



class ScooterManagerComponent:
    def publish_message(self, msg):
        payload = json.dumps(msg)
        self.mqtt_client.publish(MQTT_TOPIC_INPUT, payload=payload, qos=2)

    def on_connect(self, client, userdata, flags, rc):
        self._logger.debug('MQTT connected to {}'.format(client))
        client.subscribe(MQTT_TOPIC_OUTPUT)

    def on_message(self, client, userdata, msg):
        self._logger.debug('Incoming message to topic {}'.format(msg.topic))
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            self._logger.info(f"Received: {payload}")
        except Exception as err:
            self._logger.error('Message sent to topic {} had no valid JSON. Message ignored. {}'.format(msg.topic, err))
            return
        command = payload.get('command')
        self._logger.debug('Command in message is {}'.format(command))

        if not command:
            self._logger.error("Message has no command")

        elif command == 'get_location':
            try:
                print(f"Received: {command}")
                escooter_name = payload.get("escooter_name")
                server_name = payload.get("server_name")
                phone_location = payload.get("phone_location")
                self.escooter_logic[escooter_name].provide_location(server_name, phone_location)
                self.escooter_stm[payload.get("escooter_name")].send("server_location_request")

            except Exception as err:
                self._logger.error('Invalid arguments to command. {}'.format(err))

        elif command == 'receive_route_details':
            try:
                print(f"Received: {command}")
                server_name = payload.get("server_name")
                destination = payload.get("destination")
                price = payload.get("price")
                self.escooter_logic[server_name].receive_server_request(destination, price)
                self.escooter_stm[payload.get("escooter_name")].send("received_route_details")

            except Exception as err:
                self._logger.error('Invalid arguments to command. {}'.format(err))

        elif command == 'destination_reached':
            try:
                print(f"Received: {command}")
                self.escooter_stm[payload.get("escooter_name")].send("arrived")

            except Exception as err:
                self._logger.error('Invalid arguments to command. {}'.format(err))
        else:
            print(f"Command ignored: {command}")

    def __init__(self, num_scooters):
        self._logger = logging.getLogger(__name__)
        print('logging under name {}.'.format(__name__))
        self._logger.info('Starting Component')
        self._logger.debug('Connecting to MQTT broker {} at port {}'.format(MQTT_BROKER, MQTT_PORT))
        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message
        self.mqtt_client.connect(MQTT_BROKER, MQTT_PORT)
        self.mqtt_client.subscribe(MQTT_TOPIC_INPUT)
        self.mqtt_client.loop_start()

        self.escooter_logic = {}
        self.escooter_stm = {}
        self.driver = stmpy.Driver()
        self.stm_driver = stmpy.Driver()
        self.escooters = {}

        for i in range(num_scooters):
            name = f"escooter_{i + 1}"
            self.escooter_logic[name] = ScooterLogic(name, None, self)
            self.escooter_stm[name] = self.escooter_logic[name].create_machine(self.escooter_logic[name], None, self)

            self.stm_driver.add_machine(self.escooter_stm[name])

        self.stm_driver.start()
        print(f"{num_scooters} e-scooters initialized.")
        self._logger.debug('Component initialization finished')

    def stop(self):
        self.mqtt_client.loop_stop()
        self.stm_driver.stop()


debug_level = logging.DEBUG
logger = logging.getLogger(__name__)
logger.setLevel(debug_level)
ch = logging.StreamHandler()
ch.setLevel(debug_level)
formatter = logging.Formatter('%(asctime)s - %(name)-12s - %(levelname)-8s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

s = ScooterManagerComponent(num_scooters=3)