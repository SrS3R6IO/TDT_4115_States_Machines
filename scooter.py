import paho.mqtt.client as mqtt
import stmpy
import logging
from threading import Thread
import json

MQTT_BROKER = 'mqtt20.iik.ntnu.no'
MQTT_PORT = 1883

MQTT_TOPIC_INPUT = 'team02Input'
MQTT_TOPIC_OUTPUT = 'team02Output'

#TODO: Ensure that the connection with server is one scooter per server (for this demo/project)?
class ScooterLogic:
    def __init__(self, name, func, component):
        self._logger = logging.getLogger(__name__)
        self.name = name
        self.func = func
        self.component = component

    def create_machine(timer_name, func, component):

        # initial transition
        scooter_logic = ScooterLogic(name=scooter_name, func=func, component=component)
        t0 = {
            "source": "initial",
            "target": "await_server_request",
            "effect": "listen_for_server_request",
        }

        # await_server_request -> await_route_details
        t1 = {
            "trigger": "server_location_request",
            "source": "await_server_request",
            "target": "await_route_details",
            "effect": "provide_location",
        }

        # await_route_details -> end/await_server_request
        t2 =  {
            'trigger':'route_received',
            'source':'await_route_details',
            'function': ScooterLogic.arrived_compound_transition}

        # t2 (if/else) -> arrived(finished)
        t3 = {
            "trigger": "arrived_at_destination",
            "source": "await_route_details",
            "target": "arrived",
            "effect": "send_arrival_confirmation",
        }

        # t2 (if/else) -> await_server_request(not arrived yet)
        t3 = {
            "trigger": "else",
            "source": "await_route_details",
            "target": "await_server_request",
            "effect": "", #none?
        }
        scooter_stm = stmpy.Machine(name=scooter_name, transitions=[t0, t1, t2, t3],
                                  obj=scooter_logic)
        scooter_logic.stm = scooter_stm
        return scooter_stm
    

    def arrived_compound_transition(self):
        #TODO but should be something like this for compound_transition
        if current_location == destination_location:
            return 'arrived_at_destination'
        else:
            return 'else'
        
    def listen_for_server_request(self):
        #TODO
        pass

    def provide_location(self):
        #TODO
        pass

    def send_arrival_confirmation(self):
        #TODO
        pass


class ScooterManagerComponent:
    def on_connect(self, client, userdata, flags, rc):
        self._logger.debug('MQTT connected to {}'.format(client))

    def on_message(self, client, userdata, msg):
        self._logger.debug('Incoming message to topic {}'.format(msg.topic))
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception as err:
            self._logger.error('Message sent to topic {} had no valid JSON. Message ignored. {}'.format(msg.topic, err))
            return
        command = payload.get('command')
        self._logger.debug('Command in message is {}'.format(command))

        if not command:
            self._logger.error("Message has no command")

        #TODO: Add all possible commands (but is possibly only get_location for scooter?)
        elif command == 'get_location':
            try:
                #TODO: Provide location from scooter to server to phone? or handle only from server?
                self.stm_driver.add_machine(timer_stm)
            except Exception as err:
                self._logger.error('Invalid arguments to command. {}'.format(err))


    def __init__(self):
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
        self.stm_driver = stmpy.Driver()
        self.stm_driver.start(keep_active=True)
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

s = ScooterManagerComponent()