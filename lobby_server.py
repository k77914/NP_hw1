# python3 server_send_recv.py
import socket, threading, json, struct, sys, time, os, queue, tempfile, copy

# ================== JSON 緩衝層（單一 writer + 原子覆寫） ==================
class UserDB:
    def __init__(self, path: str, commit_interval: float = 0.5, max_batch: int = 64):
        self.path = path
        self.commit_interval = commit_interval
        self.max_batch = max_batch

        self._lock = threading.RLock()     # 保護 self._state
        self._q = queue.Queue()            # 更新請求佇列
        self._state = self._load_file()    # 記憶體狀態

        self._stop_evt = threading.Event()
        self._writer = threading.Thread(target=self._writer_loop, daemon=True)
        self._writer.start()

    # ---- 對外 API ----
    def load_all(self) -> dict:
        """取得 userlist 的快照（讀鎖保護，回傳 deepcopy 避免被外部改動）。"""
        with self._lock:
            return copy.deepcopy(self._state)

    def update_user(self, user: str, password: str = None, status: str = None,
                    win_delta: int = 0, total_delta: int = 0):
        """排程一筆使用者更新（不存在則自動建立）。"""
        self._q.put(("update_user", (user, password, status, win_delta, total_delta)))

    def set_all_offline_sync(self):
        """啟動時把所有使用者設為 offline（同步，啟 client 接受前呼叫較單純）。"""
        with self._lock:
            for u in self._state.values():
                u["status"] = "offline"
            self._atomic_write(self._state)

    def shutdown(self):
        """結束時呼叫，確保 flush。"""
        self._q.put(("__stop__", None))
        self._stop_evt.wait(timeout=3.0)

    # ---- 內部：writer thread ----
    def _writer_loop(self):
        dirty = False
        batch = 0
        last_flush = time.time()

        while True:
            timeout = max(0.0, self.commit_interval - (time.time() - last_flush))
            try:
                op, args = self._q.get(timeout=timeout)
            except queue.Empty:
                op = None

            if op is None:
                # 逾時：視情況 flush
                if dirty:
                    with self._lock:
                        self._atomic_write(self._state)
                    dirty = False
                    batch = 0
                    last_flush = time.time()
                continue

            if op == "__stop__":
                if dirty:
                    with self._lock:
                        self._atomic_write(self._state)
                self._stop_evt.set()
                return

            if op == "update_user":
                user, password, status, win_d, total_d = args
                with self._lock:
                    rec = self._state.get(user)
                    if rec is None:
                        rec = {
                            "status": status if status is not None else "offline",
                            "password": password if password is not None else "",
                            "total_game": 0,
                            "win": 0,
                        }
                        self._state[user] = rec
                    else:
                        if status is not None:
                            rec["status"] = status
                        if password is not None and password != "":
                            rec["password"] = password
                        # 依原本語意累加
                        rec["win"] += int(win_d)
                        rec["total_game"] += int(total_d)
                dirty = True
                batch += 1

                # 批次門檻達成就立刻寫檔
                if batch >= self.max_batch:
                    with self._lock:
                        self._atomic_write(self._state)
                    dirty = False
                    batch = 0
                    last_flush = time.time()

    # ---- file I/O ----
    def _load_file(self) -> dict:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 防呆：結構校正
                if not isinstance(data, dict):
                    return {}
                return data
        except (json.JSONDecodeError, OSError):
            return {}

    def _atomic_write(self, data: dict):
        """臨時檔寫入 → flush+fsync → os.replace 原子換檔。"""
        dir_ = os.path.dirname(self.path) or "."
        fd, tmp = tempfile.mkstemp(prefix=".tmp_", dir=dir_, text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        finally:
            try:
                os.remove(tmp)
            except FileNotFoundError:
                pass


# ================== tool and network logic ==================
def set_keepalive(sock):
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    try:
        import platform
        if platform.system() == "Linux":
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 20)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
    except Exception:
        pass

def recvn(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("peer closed")
        buf += chunk
    return buf

def send_json(sock: socket.socket, obj: dict):
    body = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    hdr = struct.pack("!I", len(body))
    sock.sendall(hdr + body)


# ====== 將你原本的 load/save 改成呼叫 DB（其餘呼叫點不用改） ======
DB: UserDB | None = None  # 會在 main() 初始化

def load_users():
    return DB.load_all()

def save_users(user, password, status="offline", win=0, total_game=0):
    # 只排入緩衝，由 writer thread 序列化套用與寫回
    DB.update_user(user, password, status, win, total_game)


def register(username, password):
    userlist = load_users()
    if username in userlist:
        msg = {"type":"error","detail":"account_exist, please change another username"}
    else:
        save_users(username, password)
        msg = {"type":"register_ok", "username":username}
    return msg

def login(username, password):
    userlist = load_users()
    u = ""
    if username in userlist and userlist[username].get("password") == password:
        if userlist[username].get("status") != "offline":
            print("user already login")
            return {"type":"error","detail":"user already login"}, u
        save_users(username, password, status="lobby")
        u = username
        msg = {"type":"login_ok"}
    else:
        msg = {"type":"error","detail":"login fail, wrong username or password"}
    return msg, u


def handle_client(conn: socket.socket, addr):
    set_keepalive(conn)
    print(f"[*] connected from {addr}")
    username = ""
    try:
        send_json(conn, {"type": "welcome", "login" : False})
        while True:
            hdr = recvn(conn, 4)
            length = struct.unpack("!I", hdr)[0]
            if length > 10_000_000:
                send_json(conn, {"type":"error","err":"payload_too_large"})
                break

            data = recvn(conn, length)
            try:
                msg = json.loads(data.decode("utf-8"))
            except json.JSONDecodeError as e:
                send_json(conn, {"type": "error", "err": "bad_json", "detail": str(e)})
                continue

            print("recv from:", addr, "msg: " ,msg)
            player_status = msg["status"]
            operation = msg["operation"]

            if player_status == "init":
                if operation == "register":
                    try:
                        u = msg["username"]; p = msg["password"]
                    except KeyError as ke:
                        send_json(conn, {"type":"error","err":f"missing_field:{ke.args[0]}"})
                        continue
                    resp = register(u, p)

                elif operation == "login":
                    try:
                        u = msg["username"]; p = msg["password"]
                    except KeyError as ke:
                        send_json(conn, {"type":"error","err":f"missing_field:{ke.args[0]}"})
                        continue
                    resp, username = login(u, p)

                elif operation == "exit":
                    send_json(conn, {"type":"exit"})
                    break
                else:
                    resp = {"type":"error","detail":"unknown_operation"}
                send_json(conn, resp)

            elif player_status == "lobby":
                if operation == "match":
                    resp = {"type":"match_ok","detail":"matching..."}
                elif operation == "create_room":
                    resp = {"type":"create_room_ok","detail":"room created"}
                elif operation == "show_profile":
                    if username == "":
                        resp = {"type":"error","detail":"user not login"}
                    else:
                        userlist = load_users()
                        profile = userlist.get(username, {})
                        resp = {
                            "type": "profile",
                            "username": username,
                            "win": profile.get("win", 0),
                            "total_games": profile.get("total_game", 0)
                        }
                elif operation == "logout":
                    if username != "":
                        save_users(username, None, status="offline")  # only modify status
                    resp =  {"type":"logout"}
                    username = ""
                else:
                    resp = {"type":"error","detail":"unknown_operation"}
                send_json(conn, resp)

            elif player_status == "waiting":
                print("recv join_game from ", addr)
                if operation == "back":
                    resp = {"type":"back","detail":"matching fail"}
                elif operation == "join_game":
                    resp = {"type":"join_game", "detail":"join a game"}
                    save_users(username, None, status="gaming", total_game=1)
                else:
                    resp = {"type":"error","detail":"unknown_operation"}
                print("send to ", addr, "msg: ", resp)
                send_json(conn, resp)

            elif player_status == "gaming":
                if operation == "check_connect":
                    resp = {"type":"ACK", "detail": "Still Connect"}
                elif operation == "end_game":
                    save_users(username, None, status="lobby", win=msg["win"])
                    resp = {"type":"back", "detail": "end game and go back to the lobby."}
                else:
                    resp = {"type":"error","detail":"unknown_operation"}
                send_json(conn, resp)

            else:
                send_json(conn, {"type":"echo","recv":msg})

    except (ConnectionError, OSError) as e:
        print(f"[!] {addr} disconnected: {e}")
        if username != "":
            save_users(username, None, status="offline")
    finally:
        try: conn.shutdown(socket.SHUT_RDWR)
        except: pass
        conn.close()
        print(f"[*] closed {addr}")


USER_FILE = "userlist.json"
HOST = "0.0.0.0"
PORT = 10099

def main():
    global DB
    DB = UserDB(USER_FILE, commit_interval=0.5, max_batch=64)
    DB.set_all_offline_sync()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((HOST, PORT))
        srv.listen(128)
        print(f"[*] Listening on {HOST}:{PORT}")

        while True:
            conn, addr = srv.accept()
            th = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            th.start()

if __name__ == "__main__":
    try:
        main()
    finally:
        if DB is not None:
            DB.shutdown()
