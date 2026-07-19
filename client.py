import argparse
import socket


def send_command(host: str, port: int, command: str) -> str:
    with socket.create_connection((host, port), timeout=2) as s:
        if not command.endswith("\n"):
            command = command + "\n"
        s.sendall(command.encode("utf-8"))
        try:
            s.shutdown(socket.SHUT_WR)
        except Exception:
            pass
        data = s.recv(4096)
        return data.decode("utf-8")


def repl(host: str, port: int) -> None:
    print(f"Connected demo client (one command per TCP connection) -> {host}:{port}")
    print("Type 'exit' or Ctrl-C to quit. Examples: SET a 1 30, GET a, QUIT")
    try:
        while True:
            line = input('> ').strip()
            if not line:
                continue
            if line.lower() in ("exit", "quit"):
                break
            try:
                resp = send_command(host, port, line)
                print(resp)
            except Exception as e:
                print('Error:', e)
    except KeyboardInterrupt:
        print('\nbye')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', default=6380, type=int)
    parser.add_argument('--cmd', help='Send a single command and exit')
    args = parser.parse_args()
    if args.cmd:
        print(send_command(args.host, args.port, args.cmd))
    else:
        repl(args.host, args.port)


if __name__ == '__main__':
    main()
