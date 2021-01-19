# encoding=latin1

import socket
import select


class Server:
	def __init__(self, host: str, port: int):
		self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.ADDRESS = (host, port)
		self.connections = []
		self.BUFSIZE = 1024
		self.start_listening()

	def start_listening(self):
		self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		self.socket.bind(self.ADDRESS)
		self.connections.append(self.socket)

		self.socket.listen()

	def get_sock_info(self, sock: socket.socket) -> str:
		if sock == self.socket:
			return "server socket"
		return ":".join(str(_) for _ in sock.getpeername())

	def handle_data(self, data: bytes):
		# TODO : log ou qqch comme ça
		print(data.decode(encoding="latin-1", errors="ignore"), end="")

	def serve(self):
		with self.socket as sock:
			print("Listening")

			while True:
				rd, _, __ = select.select(self.connections, [], [])

				for other in rd:
					other: socket.socket
					if other == sock:
						conn, _ = sock.accept()
						print(f"Connected to {_[0]}:{_[1]}")
						self.connections.append(conn)
					else:
						try:
							data = other.recv(self.BUFSIZE)

						except ConnectionResetError:
							print("Logger instance ended the connection")
							other.close()
							self.connections.remove(other)
							continue

						if data:
							self.handle_data(data)
							other.send(b"OK")

						else:
							print(f"\nConnection to {self.get_sock_info(other)} lost")
							self.connections.remove(other)
							other.close()


if __name__ == '__main__':
	server = Server("0.0.0.0", 9001)
	server.serve()
