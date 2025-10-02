# python3 client_send_recv.py
import socket, json, struct, sys, os, time, random, select

# ---------------------
# non-blocking input helpers
# ---------------------
def _poll_user_command(_buf=[]):
    r, _, _ = select.select([sys.stdin], [], [], 0)
    if r:
        s = sys.stdin.readline()
        if s:
            s = s.strip()
            if s:
                return s
    return None

def nb_input(prompt=">>>> "):
    print(prompt, end="", flush=True)
    buf_lower = None
    while True:
        buf_lower = _poll_user_command()
        if buf_lower is not None:
            return buf_lower  
        time.sleep(0.05)

# ---------------------
# send, recv
# ---------------------
def recvn(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("server closed")
        buf += chunk
    return buf

def send_json(sock, obj):
    body = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    sock.sendall(struct.pack("!I", len(body)) + body)

## initial page
def initpage():
    op = -1
    while op not in ["1", "2", "3"]:
        print("\n=== init_page ===")
        print("Welcome to Shadow BINGO")
        print("Please enter a 1, 2 or 3 to choose action")
        print("1. Register")
        print("2. Login")
        print("3. Exit")
        op = nb_input(">>>> ").strip()
    if op == "1":
        msg = register()
    elif op == "2":
        msg = login()
    else:
        msg = {"status": "init", "operation":"exit"}
    return msg

def register():
    print("\n=== Register ===")
    user = nb_input("Enter username: ")
    password = nb_input("Enter password: ")
    msg = {"status": "init", "operation":"register","username":user,"password":password}
    os.system("clear")
    return msg

def login():
    print("\n=== Login ===")
    user = nb_input("Enter username: ")
    password = nb_input("Enter password: ")
    msg = {"status": "init", "operation":"login","username":user,"password":password}
    os.system("clear")

    return msg

def lobby():
    op = -1
    while op not in ["1", "2", "4", "5"]:
        print("\n=== Lobby ===")
        print("1. Find an opponent")
        print("2. Create a room")
        print("3. Learning rule")
        print("4. Show profile")
        print("5. Logout")
        op = nb_input(">>>> ").strip()
        if op == "3":
            os.system('clear')
            print("\n=== Learning rule ===")
            print("The game is played on a 5x5 grid, with each player having their own grid.")
            print("Players take turns drawing numbers from a shared pool.")
            print("When a number is drawn, players mark it on their grid if they have it.")
            print("The objective is to be the first to complete three rows, columns, or diagonals of marked numbers.")
            print("The first player to achieve this shouts 'BINGO!' and wins the game.\n")
            print("However, in this version of Shadow BINGO, players can also use special abilities to hinder their opponents or enhance their own chances of winning.")
            print("Each player has a skill, SHADOW, which can be used once per game to block a number on their opponent's grid from being marked until the end of game.")
    if op == "1":
        msg = {"status": "lobby", "operation":"match"}
    elif op == "2":
        msg = {"status": "lobby", "operation":"create_room"}
    elif op == "4":
        msg = show_profile()
    elif op == "5":
        msg = logout()
    return msg

def show_profile():
    msg = {"status": "lobby", "operation":"show_profile"}
    return msg

def logout():
    msg = {"status": "lobby", "operation":"logout"}
    return msg

def match():
    #os.system('cls' if os.name == 'nt' else 'clear')
    udp_s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_s.settimeout(0.5)
    conn = None
    peer_addr = None
    server_name = ["linux1", "linux2", "linux3", "linux4"]
    accessable_server = ["140.113.17.11", "140.113.17.12", "140.113.17.13", "140.113.17.14"]
    waiting_list = []
    for sid in range(4):
        print("search on ", server_name[sid])
        for rec_port in range(10299, 14299, 200):
            #print("send invitation msg to ", server_name[sid], rec_port)
            try:
                udp_s.sendto(b'FIND', (accessable_server[sid], rec_port))
                while True:
                    try:
                        data, addr = udp_s.recvfrom(1024)
                    except socket.timeout:
                        break

                    if data.decode() == "ACK":
                        print(f"Find {addr}")
                        waiting_list.append(addr)

            
                    # 其他訊息忽略，繼續等
                    if peer_addr is not None:
                        break

            except OSError as e:
                print("Socket error:", e)
                sys.exit(1)

            # 如果有對手接受（peer_addr 設定過），就開 TCP 等對方連
            if peer_addr is not None:
    
    while conn is None and not waiting_list:
        op = ""
        while op is "" or not op.isdigit():
            id = 1
            for p in waiting_list:
                print(id, ".:", p)
                id += 1
            print("Choose one to invite / or enter leave to leave:")
            op = nb_input()
            if op == "leave":
                udp_s.close()
                return None, {"status": "waiting", "operation": "back"}
            elif op.isdigit() and 0 < int(op) <= waiting_list.count():
                break
        ## get op == id
        udp_s.sendto(b'INVITE', waiting_list[int(op)-1])
        udp_s.settimeout(20)
        try:
            data, addr = udp_s.recvfrom(1024)
        except socket.timeout:
            # 沒等到 ACCEPT/REJECT 就換下一個
            waiting_list.pop(int(op)-1)
            udp_s.settimeout(None)
            continue
        if data.decode() == "ACCEPT" and addr[1] == rec_port:
            print(f"Opponent at {addr} accepted your invitation.")
            print("Sending game TCP info...")
            udp_s.settimeout(None)
            peer_addr = addr ### ok
            
        elif data.decode() == "REJECT" and addr[1] == rec_port:
            print(f"Opponent at {addr} rejected your invitation.")
            waiting_list.pop(int(op)-1)
            udp_s.settimeout(None)
            continue




        tcp_s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        tcp_s.bind(("", 0))
        tcp_port = tcp_s.getsockname()[1]
        udp_s.sendto(f"TCP,{tcp_port}".encode(), peer_addr)
        udp_s.close()

        tcp_s.listen()
        tcp_s.settimeout(20)  # 避免無限卡在 accept
        print("Waiting for opponent to connect...")
        try:
            conn, addr = tcp_s.accept()
            print(f"Opponent connected from {addr}")
        except socket.timeout:
            print("TCP accept timeout; opponent didn't connect.")
            conn = None
    

    if conn is None:
        return None, {"status": "waiting", "operation": "back"}
    return conn, {"status": "waiting", "operation": "join_game", "other": "from match"}

def create_room():
    tcp_s = None
    for port in range(10699, 14299, 200):
        try:
            udp_s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_s.bind(("", port))
            udp_s.settimeout(0.4)  # 短 timeout，以便輪詢使用者輸入
            os.system('cls' if os.name == 'nt' else 'clear')
            print(f"Room created at UDP port {port}, waiting for opponent to join...")
            print("Tip: type 'leave' then press Enter to go back to lobby.")

            # 等待對手 FIND（期間可輸入 leave）
            while True:
                # 先檢查是否有輸入 leave
                cmd = _poll_user_command()
                if cmd == 'leave':
                    print("Leaving room and returning to lobby...")
                    udp_s.close()
                    return None, {"status": "waiting", "operation": "back"}

                try:
                    data, addr = udp_s.recvfrom(1024)
                except socket.timeout:
                    time.sleep(0.05)
                    continue

                if data.decode() == "FIND":
                    udp_s.sendto(b'ACK', addr)
                elif data.decode() == "INVITE":
                    print(f"Received game invitation from {addr}: FIND")
                    print("Accept invitation? Type 'y' to accept, 'n' to reject. (or 'leave' to go back)")

                    # 非阻塞等待 y/n/leave
                    resp = None
                    while resp not in ('y', 'n', 'leave'):
                        resp = _poll_user_command()
                        if resp is None:
                            # 同時持續收其他封包（可忽略或額外處理）
                            try:
                                data2, addr2 = udp_s.recvfrom(1024)
                                # 若又收到 FIND，可選擇回 ACK，這裡忽略重複
                                _ = data2  # noqa
                                _ = addr2  # noqa
                            except socket.timeout:
                                pass
                            time.sleep(0.05)

                    if resp == 'leave':
                        print("Leaving room and returning to lobby...")
                        udp_s.close()
                        return None, {"status": "waiting", "operation": "back"}
                    elif resp == 'y':
                        udp_s.sendto(b'ACCEPT', addr)
                        print("Invitation accepted. Waiting for game TCP info... (type 'leave' to cancel)")
                        break
                    else:
                        udp_s.sendto(b'REJECT', addr)
                        print("Invitation rejected. Waiting for new invitation...")

            # 等 TCP 資訊（期間也可 leave）
            peer = None
            tcp_port = None
            while True:
                cmd = _poll_user_command()
                if cmd == 'leave':
                    print("Canceled after accept; returning to lobby...")
                    udp_s.close()
                    return None, {"status": "waiting", "operation": "back"}

                try:
                    data, addr2 = udp_s.recvfrom(1024)
                except socket.timeout:
                    time.sleep(0.05)
                    continue

                if data.decode().startswith("TCP"):
                    _, tcp_port_str = data.decode().split(",", 1)
                    tcp_port = int(tcp_port_str)
                    peer = addr2
                    print(f"Received TCP info from {peer}, connecting to TCP port {tcp_port}...")
                    break

            # 建立 TCP 連線
            tcp_s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            tcp_s.settimeout(20)
            try:
                tcp_s.connect((peer[0], tcp_port))
                print("Connected to opponent via TCP.")
                tcp_s.settimeout(None)
            except socket.timeout:
                print("TCP connect timeout.")
                tcp_s = None

            udp_s.close()
            break

        except OSError as e:
            if e.errno == 98:  # Address already in use
                continue
            else:
                print("Socket error:", e)
                sys.exit(1)

    if tcp_s is None:
        return None, {"status": "waiting", "operation": "back"}

    return tcp_s, {"status": "waiting", "operation": "join_game", "other":"from create"}

def game(server:socket, opponent: socket, move_first:bool):
    ### check connect to the server
    print("send a pkt to check connect to server")
    if not move_first:
        time.sleep(0.5)

    send_json(server, {"status":"gaming", "operation": "check_connect"})
    n = struct.unpack("!I", recvn(server, 4))[0]
    resp = json.loads(recvn(server, n).decode("utf-8"))
    print(resp["detail"])

    play = Ingame(server, opponent, move_first)

    if not move_first:
        time.sleep(0.5)
    return play.game_result




class Ingame:
    def __init__(self, server:socket, opponent:socket, move_first): #game flow
        try:
            #### game setting
            self.bp = self.generate_map() # bingo map
            self.true_table = [[False for _ in range(5)] for _ in range(5)] # true -> show
            self.skill = 2
            self.server = server
            self.opponent = opponent
            self.banned = []
            self.win = False
            self.game_result = None
            self.use_skill_mode = False
            self.end_game = False

            num = 0

            while move_first: # send ok to opponent
                send_json(self.opponent, {"operation":"ok"})
                n = struct.unpack("!I", recvn(opponent, 4))[0]
                resp = json.loads(recvn(opponent, n).decode("utf-8"))
                if resp["operation"] == "ok": ## game start here
                    num = self.action()
                    if num != 0:
                        self.update(num)
                        self.show_map()
                        print("waiting for the opponent move ...")
                    else:
                        self.end_game = True
                    send_json(opponent, {"call":num, "use_skill":self.use_skill_mode, "win":False, "end_game":self.end_game})
                    break

            while not move_first:
                self.show_map()
                n = struct.unpack("!I", recvn(opponent, 4))[0]
                resp = json.loads(recvn(opponent, n).decode("utf-8"))
                if resp["operation"] == "ok":
                    send_json(self.opponent, {"operation":"ok"})
                    break
            # repeatly 
            while not self.end_game:
                n = struct.unpack("!I", recvn(opponent, 4))[0]
                resp = json.loads(recvn(opponent, n).decode("utf-8"))
                ####### update by recv
                if resp["win"] == True: # game over -> lose
                    self.end_game = True
                    break
                elif resp["end_game"] == True: # opponent give up the game
                    self.win = True
                    self.end_game = True
                    print("\nOpponent gave up the game, let you down")
                    break
                if not resp["use_skill"]:
                    self.update(resp["call"])
                else:
                    self.banned.append(resp["call"])

                ####### check win after opponent call
                if self.check_win():
                    self.win = True
                    send_json(opponent, {"call":num, "use_skill":self.use_skill_mode, "win":True})
                    break
                
                ###### take action
                num = self.action(resp["call"])
                if num == 0: ### -> quit
                    break
                print(type(num))
                self.update(num)
                self.show_map()

                if self.check_win():
                    self.win = True
                    send_json(opponent, {"call":num, "use_skill":self.use_skill_mode, "win":True})
                    
                    break
                else:
                    send_json(opponent, {"call":num, "use_skill":self.use_skill_mode, "win":False, "end_game":False})
                print("\nwaiting for the opponent move ...")

        except (ConnectionError, OSError, KeyboardInterrupt) as e:
            print(type(e))
            if type(e) == KeyboardInterrupt:
                os.system("clear")
                print(f"give up the game. You lose")
                print("back to the lobby")
            else:
                os.system("clear")
                print(f"[!] opponent disconnected")
                print("back to the lobby")
                self.win = True

        finally:
            try: opponent.shutdown(socket.SHUT_RDWR)
            except: pass
            opponent.close()
            print("YOU WIN!!!!" if self.win else "YOU LOSE")
            self.game_result = {"status":"gaming", "operation":"end_game", "win":self.win}
            

    def generate_map(self):
        arr = list(range(1, 26))
        random.shuffle(arr)
        bp = [[0] * 5 for _ in range(5)]
        for i in range(25):
            bp[i // 5][i % 5] = arr[i]
        return bp

    def show_map(self):
        os.system("clear")
        print("========= bingo map =========")
        for x in range(5):
            for y in range(5):
                if not self.true_table[x][y]: # False -> show
                    print("%2d"%self.bp[x][y], " ", end="")
                else:
                    print("    ", end="")
            print("")
        print("=========  status   =========")
        print("skill: ", self.skill)

    def action(self, last_call=None):
        op = None
        while op not in ["2", "3"]:
            os.system("clear")
            self.show_map()
            print("")
            print("opponent last call: ", last_call if last_call not in self.banned else "None")
            print("Mode: ", "USE" if self.use_skill_mode else "NOT USE")
            if self.skill > 0:
                print("1. switch to use skill mode" if not self.use_skill_mode else "1. switch to not use skill mode")
            else:
                print("Can't use skill")
            print("2. call a number")
            print("3. quit a game, back to lobby.")
            op = nb_input().strip()
            if op == "1":
                if self.skill > 0:
                    self.use_skill_mode = True if not self.use_skill_mode else False
        if op == "3":
            return 0
        num = "0"
        while num == "0" or not num.isdigit():
            print("enter the number:", end="")
            num = nb_input()
        if self.use_skill_mode:
            self.skill -= 1

        if self.skill <= 0:
            self.use_skill_mode = False
        return int(num)
        
    def update(self, num):
        if num in self.banned:
            return
        for x in range(5):
            for y in range(5):
                if self.bp[x][y] == num:
                    self.true_table[x][y] = True
                
    def check_win(self):
        line = 0
        # check rows
        for i in range(5):
            conti = 0
            for j in range(5):
                if self.true_table[i][j]:
                    conti += 1
                else:
                    break
            if conti == 5:
                line += 1
        # check columns
        for i in range(5):
            conti = 0
            for j in range(5):
                if self.true_table[j][i]:
                    conti += 1
                else:
                    break
            if conti == 5:
                line += 1
        # main diagonal
        conti = 0
        for i in range(5):
            if self.true_table[i][i]:
                conti += 1
            if conti == 5:
                line += 1
        # vice diagonal
        conti = 0
        for i in range(5):
            if self.true_table[i][4 - i]:
                conti += 1
            if conti == 5:
                line += 1
        return line >= 3


# parameter
SERVER_HOST = "140.113.17.11" # CSIT linux 1 server
SERVER_PORT = 10099
status = {
    "init":1,
    "lobby":2, # have login
    "matching":3,
    "waiting":4, # match or create a room
    "gaming":5 # in the game
}
### deal with the server response
with socket.create_connection((SERVER_HOST, SERVER_PORT)) as s:
    s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

    # 讀 server hello
    n = struct.unpack("!I", recvn(s, 4))[0]
    # print server msg
    print(json.loads(recvn(s, n).decode("utf-8")))
    # build the connection
    player_status = status["init"]
    move_first = False
    os.system("clear")
    while True:
        if player_status == status["init"]:
            msg = initpage()
        elif player_status == status["lobby"]:
            msg = lobby()
        elif player_status == status["matching"]:
            sock_game, msg = match()

        elif player_status == status["waiting"]:
            move_first = False
            sock_game, msg = create_room()

        elif player_status == status["gaming"]:
            msg = game(s, sock_game, move_first)
        else:
            print("=============status error=============")
            sys.exit(0)

        send_json(s, msg)
        # print(msg) debug
        # 收回覆
        n = struct.unpack("!I", recvn(s, 4))[0]
        resp = json.loads(recvn(s, n).decode("utf-8"))
        print("=============================")
        # print(resp) debug
        if resp["type"] == "error":
            print(resp["detail"])
        ############################################################### response for init
        elif player_status == status["init"]:
            if msg["operation"] == "register" and resp["type"] == "register_ok":
                os.system("clear")
                print("")
                print(f"register ok! username: {resp['username']}")

            elif msg["operation"] == "login" and resp["type"] == "login_ok":
                os.system("clear")
                print("")
                print(f"login ok!, hello {msg['username']}")
                player_status = status["lobby"]

            elif msg["operation"] == "exit" and resp["type"] == "bye":
                os.system("clear")
                print("")
                print("bye! Leave system")
                break
        ##################################################################
        #                     response for lobby                         #
        ##################################################################
        elif player_status == status["lobby"]:
            if msg["operation"] == "match" and resp["type"] == "match_ok":
                print("matching...")
                player_status = status["matching"] # status change to matching

            elif msg["operation"] == "create_room" and resp["type"] == "create_room_ok":
                print("room created")
                player_status = status["waiting"] # status change to waiting

            elif msg["operation"] == "show_profile" and resp["type"] == "profile":
                os.system('clear')
                print("\n=== Profile ===")
                print(f"Username: {resp['username']}")
                print(f"Win: {resp['win']}")
                print(f"Total games: {resp['total_games']}")

            elif msg["operation"] == "logout" and resp["type"] == "bye":
                os.system('clear')
                print("bye!")
                player_status = status["init"]
        elif player_status == status["matching"]:
            print("recv server's response, matching")
            # match success
            if resp["type"] == "join_game":
                player_status = status["gaming"]
                move_first = True

            elif resp["type"] == "back":
                player_status = status["lobby"]

        elif player_status == status["waiting"]:
            print("recv server's response, waiting")
            if resp["type"] == "join_game":
                player_status = status["gaming"]

            elif resp["type"] == "back":
                player_status = status["lobby"]
        ########################################################### end game
        elif player_status == status["gaming"]:
            if resp["type"] == "back":
                player_status = status["lobby"]
