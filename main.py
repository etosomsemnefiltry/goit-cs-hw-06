import mimetypes
import pathlib
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import socket
import json
from datetime import datetime
from threading import Thread
from pymongo import MongoClient

""" 
Для запуска в консоли набираем 
docker-compose build
docker-compose up -d
Приложение станет доступным здесь http://localhost:3000/
После публикации сообщения можно убедиться, 
что оно записалось тут http://localhost:3000/get-messages

Файлы базы создаются в директории приложения. 
"""

# Подключение к MongoDB без пароля для простоты работы
mongo_uri = os.getenv("MONGO_URI")
client = MongoClient(mongo_uri)
db = client["messages_db"]
collection = db["messages"]


class HttpHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            data = self.rfile.read(int(self.headers['Content-Length']))
            data_parse = urllib.parse.unquote_plus(data.decode())
            data_dict = {key: value for key, value in [el.split('=') for el in data_parse.split('&')]}
        except Exception as e:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Invalid data format")
            print(f"Error parsing POST data: {e}")
            return

        self.send_to_socket_server(data_dict)
        self.send_response(302)
        self.send_header('Location', '/')
        self.end_headers()

    def do_GET(self):
        pr_url = urllib.parse.urlparse(self.path)
        if pr_url.path == '/':
            self.send_html_file('index.html')
        elif pr_url.path == '/message.html':
            self.send_html_file('message.html')
        elif pr_url.path == '/get_messages': # Страница для проверки, записываются ли сообещния
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            messages = list(collection.find({}, {"_id": 0}))  # Получаем все сообщения
            if messages:
                # Преобразуем список сообщений
                formatted_messages = "\n".join([json.dumps(message, ensure_ascii=False) for message in messages])
                print(f"Все сообщения:\n{formatted_messages}")  # Логируем все сообщения
                self.wfile.write(formatted_messages.encode('utf-8'))
            else:
                self.wfile.write(json.dumps({"message": "No messages found in the database."}).encode('utf-8'))
        else:
            if pathlib.Path().joinpath(pr_url.path[1:]).exists():
                self.send_static()
            else:
                self.send_html_file('error.html', 404)

    def send_html_file(self, filename, status=200):
        filepath = filename.strip('/')  # Убираем начальный слэш
        if os.path.exists(filepath):  # Проверяем наличие файла
            self.send_response(status)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            with open(filepath, 'rb') as f:
                self.wfile.write(f.read())
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'<h1>404 Not Found</h1>')

    def send_static(self):
        if os.path.exists(f'.{self.path}'):
            self.send_response(200)
            mt = mimetypes.guess_type(self.path)
            if mt:
                self.send_header("Content-type", mt[0])
            else:
                self.send_header("Content-type", 'text/plain')
            self.end_headers()
            with open(f'.{self.path}', 'rb') as file:
                self.wfile.write(file.read())
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"File not found")

    def send_to_socket_server(self, data):
        # Отправка данных в сокет-сервер
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect(('127.0.0.1', 5000))
                sock.sendall(json.dumps(data).encode('utf-8'))
                print("Socket. Data sent")
        except ConnectionRefusedError:
            print("Socket server disabled.")
        except Exception as e:
            print(f"Error socket server: {e}")

def run(server_class=HTTPServer, handler_class=HttpHandler):
    server_address = ('', 3000)
    http = server_class(server_address, handler_class)
    try:
        print('HTTP Server running on port 3000')
        http.serve_forever()
    except KeyboardInterrupt:
        http.server_close()

def run_socket():
    db = client["messages_db"]
    collection = db["messages"]

    host = '127.0.0.1'
    port = 5000
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((host, port))
    sock.listen(1)
    sock.settimeout(10)
    print(f"Socket server running ws://{host}:{port}")

    while True:
        conn = None
        try:
            conn, addr = sock.accept()
            print(f"Connection established with {addr}")
            data = conn.recv(1024)
            if data:
                message = json.loads(data.decode('utf-8'))
                message['date'] = str(datetime.now())
                try:
                    collection.insert_one(message)
                    print(f"Message saved to MongoDB: {message}")
                except Exception as e:
                    print(f"Error saving message to MongoDB: {e}")
                conn.sendall(b"Message received")
        except socket.timeout:
            pass
        except Exception as e:
            print(f"Socket server error: {e}")
        finally:
            if conn:
                conn.close()

if __name__ == '__main__':
    # Запуск HTTP-сервера и сокет-сервера
    http_thread = Thread(target=run)
    socket_thread = Thread(target=run_socket)

    http_thread.start()
    socket_thread.start()

    http_thread.join()
    socket_thread.join()