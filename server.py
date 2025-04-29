import paho.mqtt.client as mqtt
import logging
import json
from stmpy import Driver, Machine
from collections import defaultdict

NUM_SCOOTERS = 3

MQTT_BROKER = 'mqtt20.iik.ntnu.no'
MQTT_PORT = 1883
MQTT_TOPIC_INPUT = 'team02Input'
MQTT_TOPIC_OUTPUT = 'team02Output'


def calculate_price(distance):
    return distance * 0.05


def calculate_distance(source, destination):
    return (abs(destination[0] - source[0]) + abs(destination[1] - source[1])) / 2


class ServerLogic:
    def __init__(self, name, component):
        self._logger = logging.getLogger(__name__)
        self.name = name
        self.component = component
        self.stm = None
        self.destination = None

        self.escooters = []

    def send_nearby_escooters(self, phone_location):
        # send list of dict of escooters with locations and distances

        distance = []
        available_escooters = []

        for escooter in self.escooters:
            if not escooter["busy"]:
                distance.append(calculate_distance(phone_location, escooter["location"]))
                available_escooters.append(escooter)
        msg = {
            "command": "escooters_list",
            "escooters": available_escooters,
            "distance": distance
        }

        self.component.publish_message(msg)

    def get_escooter(self, escooter_id):
        for i in range(len(self.escooters)):
            if escooter_id == self.escooters[i]["id"]:
                self.escooters[i]["busy"] = self.name

    def receive_destination(self, phone_location, destination):
        distance = calculate_distance(phone_location, destination)
        price = calculate_price(distance)
        self.component.publish_message({"command": "suggest_route", "distance": distance, "price": price})

    def price_remaining(self, phone_location):
        price = 2 * calculate_distance(phone_location, self.destination)
        self.component.publish_message({"command": "price_remaining", "price": price})

    def remaining_distance(self, phone_location):
        distance = calculate_distance(phone_location, self.destination)
        self.component.publish_message({"command": "distance_remaining", "distance": distance})


class ServerManagerComponent:
    """
    The component to manage named phones.

    This component connects to an MQTT broker and listens to commands.
    To interact with the component, do the following:

    * Connect to the same broker as the component. You find the broker address
    in the value of the variable `MQTT_BROKER`.
    * Subscribe to the topic in variable `MQTT_TOPIC_OUTPUT`. On this topic, the
    component sends its answers.
    * Send the messages listed below to the topic in variable `MQTT_TOPIC_INPUT`.

        {"command": "phone_request", "name": "spaghetti", "duration":50}

        {"command": "status_all_timers"}

        {"command": "status_single_timer", "name": "spaghetti"}

    """

    def __init__(self):
        # get the logger object for the component
        self._logger = logging.getLogger(__name__)
        print('logging under name {}.'.format(__name__))
        self._logger.info('Starting Component')

        # create a new MQTT client
        self._logger.debug('Connecting to MQTT broker {} at port {}'.format(MQTT_BROKER, MQTT_PORT))
        self.mqtt_client = mqtt.Client()
        # callback methods
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message
        # Connect to the broker
        self.mqtt_client.connect(MQTT_BROKER, MQTT_PORT)
        # subscribe to proper topic(s) of your choice
        self.mqtt_client.subscribe(MQTT_TOPIC_INPUT)
        # start the internal loop to process MQTT messages
        self.mqtt_client.loop_start()

        # we start the stmpy driver, without any state machines for now
        self.server_logic = {}
        self.server_stm = {}
        self.stm_driver = {}

        # List of escooters
        self.escooters = []
        # Number of escooters that have responded the message
        self.counter = defaultdict(int)

        for i in range(NUM_SCOOTERS):
            self.escooters.append(f"escooter_{i + 1}")

    def on_connect(self, client, userdata, flags, rc):
        # we just log that we are connected
        self._logger.debug('MQTT connected to {}'.format(client))

    def on_message(self, client, userdata, msg):
        """
        Processes incoming MQTT messages.

        We assume the payload of all received MQTT messages is an UTF-8 encoded
        string, which is formatted as a JSON object. The JSON object contains
        a field called `command` which identifies what the message should achieve.

        As a reaction to a received message, we can for example do the following:

        * create a new state machine instance to handle the incoming messages,
        * route the message to an existing state machine session,
        * handle the message right here,
        * throw the message away.

        """
        self._logger.debug('Incoming message to topic {}'.format(msg.topic))

        # unwrap JSON-encoded payload
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception as err:
            self._logger.error('Message sent to topic {} had no valid JSON. Message ignored. {}'.format(msg.topic, err))
            return
        command = payload.get('command')
        self._logger.debug('Command in message is {}'.format(command))

        if not command:
            self._logger.error("Message has no command")

        elif command == "receive_escooter_location":
            try:
                escooter_location = payload.get('location')
                escooter_id = payload.get('escooter_id')
                escooter_busy = payload.get('escooter_busy')
                server_name = payload.get('server_name')
                self.server_logic[server_name].escooters.append(
                    {"id": escooter_id, "location": escooter_location, "busy": escooter_busy})
                self.counter[server_name] += 1

                if self.counter[server_name] == len(self.escooters):
                    phone_location = payload.get('location')
                    self.server_logic[server_name].send_nearby_escooters(phone_location)
                    # send trigger to internal transition to move states
                    self.stm_driver[server_name].send('received_escooters_location', server_name)

            except Exception as err:
                self._logger.error('Invalid arguments to command. {}'.format(err))


        elif command == 'phone_location':  # starting server state machine and first transition
            try:
                server_name = payload.get('phone_name')
                exist = False
                phone_location = payload.get('location')
                for server, logic in self.server_logic.items():
                    if server == server_name:
                        print("This phone already requested info")
                        exist = True
                if not exist:
                    # create a new instance of the timer logic state machine
                    self.server_logic[server_name] = ServerLogic(name=server_name, component=self)
                    self.server_stm[server_name] = self.server_logic[server_name].create_machine(server_name, self)
                    # add the machine to the driver to start it
                    self.stm_driver[server_name] = Driver()
                    self.stm_driver[server_name].start(keep_active=True)
                    self.stm_driver[server_name].add_machine(self.server_stm[server_name])

                    self._logger.info(f"Server {server_name}, has been started")

                    for escooter in self.escooters:
                        print("Sent command get location")
                        self.publish_message(
                            {"command": "get_location", "escooter_name": escooter, "server_name": server_name,
                             "phone_location": phone_location})

                    self.stm_driver[server_name].send("exchange_phone_location", server_name)
            except Exception as err:
                self._logger.error('Invalid arguments to command. {}'.format(err))

        elif command == 'selected_escooter':
            try:
                server_name = payload.get('phone_name')
                escooter_id = payload.get("escooter")  # save id for calculation later
                print(payload)
                self.server_logic[server_name].get_escooter(escooter_id)

                self.stm_driver[server_name].send('selected_escooter', server_name)
            except Exception as err:
                self._logger.error('Invalid arguments to command. {}'.format(err))



        elif command == 'exchange_destination':
            try:
                server_name = payload.get('phone_name')
                self.server_logic[server_name].destination = payload.get('destination')
                self.server_logic[server_name].receive_destination(payload.get('location'),
                                                                   self.server_logic[server_name].destination)
                self.stm_driver[server_name].send('received_destination', server_name)
            except Exception as err:
                self._logger.error('Invalid arguments to command. {}'.format(err))

        elif command == 'route_confirmed':
            try:
                server_name = payload.get('phone_name')
                confirmed = payload.get('confirm')
                if confirmed:
                    self.stm_driver[server_name].send('route_accepted', server_name)
                else:
                    self.stm_driver[server_name].send('route_declined', server_name)
            except Exception as err:
                self._logger.error('Invalid arguments to command. {}'.format(err))

        elif command == "ask_price":
            try:
                server_name = payload.get('phone_name')
                self.stm_driver[server_name].send('request_price_distance', server_name)
                phone_location = payload.get('location')
                self.server_logic[server_name].price_remaining(phone_location)
            except Exception as err:
                self._logger.error('Invalid arguments to command. {}'.format(err))

        elif command == "ask_distance":
            try:
                server_name = payload.get('phone_name')
                self.stm_driver[server_name].send('request_price_distance', server_name)
                self.server_logic[server_name].remaining_distance(payload.get("location"))
            except Exception as err:
                self._logger.error('Invalid arguments to command. {}'.format(err))

        elif command == "destination_reached":
            try:
                server_name = payload.get('phone_name')
                self.stm_driver[server_name].send("destination_reached", server_name)
                self.server_logic.pop(server_name)
            except Exception as err:
                self._logger.error('Invalid arguments to command. {}'.format(err))

        else:
            self._logger.error('Unknown command {}. Message ignored.'.format(command))

    def publish_message(self, msg):

        payload = json.dumps(msg)
        self.mqtt_client.publish(MQTT_TOPIC_OUTPUT, payload=payload, qos=2)

    def stop(self, server_name):
        """
        Stop the component.
        """
        # stop the MQTT client
        self.mqtt_client.loop_stop()

        # stop the state machine Driver
        self.stm_driver[server_name].stop()


def create_machine(self, server_name, component):
    # initial transition -> WaitPhoneRequest
    t0 = {
        "source": "initial",
        "target": "WaitPhoneRequest"
    }
    # WaitPhoneRequest -> SearchForNearbyEscooters
    t1 = {
        "trigger": "exchange_phone_location",
        "source": "WaitPhoneRequest",
        "target": "waiting_escooters_location",
        # "effect": "send_escooters_nearby(phone_location)"
    }
    # SearchForNearbyEscooters -> AwaitDestination
    t2 = {
        "trigger": "selected_escooter",
        "source": "SearchForNearbyEscooters",
        "target": "AwaitDestination"
    }
    # AwaitDestination -> AwaitRouteConfirmation
    t3 = {
        "trigger": "received_destination",
        "source": "AwaitDestination",
        "target": "AwaitRouteConfirmation"
    }
    # AwaitRouteConfirmation -> Traveling (if statement)
    t4 = {
        "trigger": "route_accepted",
        "source": "AwaitRouteConfirmation",
        "target": "Traveling"
    }
    # AwaitRouteConfirmation -> AwaitDestination (else statement)
    t5 = {
        "trigger": "route_declined",
        "source": "AwaitRouteConfirmation",
        "target": "AwaitDestination"
    }
    # Travelling -> Traveling (send price and route)
    t6 = {
        "trigger": "request_price_distance",
        "source": "Traveling",
        "target": "Traveling",
        # "effect": "send_price(), send_distance()"
    }
    # Travelling -> WaitPhoneRequest
    t7 = {
        "trigger": "user_out_of_bounds_exception",
        "source": "Traveling",
        "target": "WaitPhoneRequest"
    }
    # Travelling -> WaitPhoneRequest
    t8 = {
        "trigger": "destination_reached",
        "source": "Traveling",
        "target": "final"
    }
    t9 = {
        "trigger": "received_escooters_location",
        "source": "waiting_escooters_location",
        "target": "SearchForNearbyEscooters"
    }
    """
    # States
    WaitPhoneRequest = {"name": "WaitPhoneRequest", 
                        "entry": "" }
    SearchForNearbyEscooters = {"name": "SearchForNearbyEscooters", 
                                "entry": "send_escooters_nearby" }
    AwaitDestination = {"name": "AwaitDestination", 
                        "entry": "" }
    AwaitRouteConfirmation = {"name": "AwaitRouteConfirmation", 
                                "entry": "calculate_route; send_route; send_price" }
    Traveling = {"name": "Traveling", 
                    "entry": "send_price; send_route" }
    """
    server_stm = Machine(name=server_name, transitions=[t0, t1, t2, t3, t4, t5, t6, t7, t8, t9], obj=self)
    self.stm = server_stm
    return server_stm


ServerLogic.create_machine = create_machine

if __name__ == '__main__':
    # logging.DEBUG: Most fine-grained logging, printing everything
    # logging.INFO:  Only the most important informational log items
    # logging.WARN:  Show only warnings and errors.
    # logging.ERROR: Show only error messages.
    debug_level = logging.DEBUG
    logger = logging.getLogger(__name__)
    logger.setLevel(debug_level)
    ch = logging.StreamHandler()
    ch.setLevel(debug_level)
    formatter = logging.Formatter('%(asctime)s - %(name)-12s - %(levelname)-8s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    s = ServerManagerComponent()

    try:
        input("Server is running. Press Enter to exit.\n")
    except Exception as e:
        raise ValueError("Error", e)

