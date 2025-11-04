import zmq
import time

# Create a context and a PUB socket
context = zmq.Context()
socket = context.socket(zmq.PUB)
socket.bind("tcp://*:5555")  # Bind to a port to listen for subscribers

# Allow some time for subscribers to connect
time.sleep(1)

# Publish a message
while True:
    message = "Hello, Subscriber!"
    socket.send_string(message)
    print(f"Sent: {message}")
    time.sleep(1)  # Send a message every second