Author      : 蔡烝旭
Student ID: 112550099
Language : Python
Github link: https://github.com/k77914/NP_hw1
# System Architecture with Communication detail

## DB
### file structure
使用json檔案儲存使用者的資訊，主要由lobby server 進行管理。
```json
file: "userlist.json"
{
	username : {
		"status":  // 紀錄使用者目前的狀態
		"password": // 密碼
		"total_game":// 總遊戲場次
		"win":  // 勝利場次
	}
}
```
### DB management
在DB 管理上，管理系統是架設在Lobby server 上，統一由其進行管理，設立外部與內部的API。
#### 外部
提供給 lobby server 對於 DB 的抽象化管理。
1. load_all : 取得userlist 的副本
2. update_user : 更新 userlist 
3. set_all_offline_sync : 在啟動時將所有user "status"設置為 "offline"
4. shutdown : 確保 flush
#### 內部
對於外部API 的實際實作，避免許多client 同時請求狀態更新，造成userlist 毀損。
1. writer_loop : 外部API 會利用任務佇列，將對於檔案的操作排入其中，writer_loop要做的事情就是維持目前的副本，然後等到更新數量累積到一定程度後，lock住檔案後atomic_write。
2. load_file : 載入檔案
3. atomic_write : 利用 atomic write 的方式，寫在 temp 上，確認沒問題後替換userlist。
## Lobby server

### helper function
#### network logic
因為linux TCP socket 的 keepalive 判定比較長(2 hr)，為了更積極的去探測對方是否斷線，設定三個參數。
* TCP_KEEPIDLE, 60 : 閒置 60s 會開始送探測pkg
* TCP_KEEPINTVL, 20 : 接著每20s 送一個探測pkg
* TCP_KEEPCNT, 3 : 連續3次沒有回，就會判定失聯
#### tool
因為整個communication 是靠 Json 型式的傳遞，以兩個函式 `recvn`, `send_json` 來協助簡化傳輸。
* recvn : 收到完整的pkg 後才會返還。
* send_json : 將訊息寄出。
### listener
綁定在 host IP address: "0.0.0.0", port: 10099. 使他監聽所有interface的封包。
若有接收到連線請求，則會開啟另一條thread (client_handler)去處理這個連線。
### client_handler
為單一的thread，主要負責該連線的事宜。
#### Route
根據client 傳入的 msg 去決定路由後。
根據其操作等反饋回應 resp 給 client。
```json
msg 架構 
{
	"status" : // 顯示 client 目前在哪個狀態 -> player_status = msg["status"]
	"operation" : // client 請求的操作
	+ 操作附帶的參數等... 
}
```
```json
resp 架構
{
	"type" : // 顯示回傳的resp 型別
	"detail" : // 協助 debug 用 有時有 有時沒有
	+ 操作附帶的參數等 ...
}
```

*player_status* : 取決於 client 寄送的 msg 中 "status" 的欄位。
*更改使用者狀態* : 改動 userlist 中 "status" 的欄位。（`offline`, `lobby`, `gaming`）
##### player_status == "init"
表示client 現在在init page （未登入）中，Lobby server 會收到三種operation。
1. register 
	提供使用者註冊帳號，msg 中會帶有 `username`, `password` 等資訊
	lobby server 會去檢查是否有相同的帳號名。
	1. Not
		註冊成功，回傳 `resp = {"type":"register_ok", "username":username}`
	2. Yes
		註冊失敗，回傳 `resp = {"type":"error","detail":"account_exist, please change another username"}`
2. login 
	提供使用者登入，msg中會帶有 `username`, `password` 等資訊
	lobby server 會去檢查該帳號是否存在、密碼是否正確、是否已經登入等等
	1. 登入成功
		回傳 `resp = {"type":"login_ok"}`
		更改使用者狀態 `offline` -> `lobby`。
	2. 登入失敗
		1. 已經登入 : `resp = {"type":"error","detail":"user already login"}`
		2. 帳號不存在 or 密碼錯誤: `resp = {"type":"error","detail":"login fail, wrong username or password"}`
3. exit
	讓使用者離開，回傳 `resp = {"type":"logout"}` ， 中斷該連線。
##### player_status == "lobby"
表示client 目前已經登入，Lobby server 會收到四種operation。
1. match
	只是一個過渡，方便Client 做狀態變更，Lobby server 收到後直接回傳 	
	`resp = {"type":"match_ok","detail":"matching..."}`
2. create_room
	只是一個過渡，方便Client 做狀態變更，Lobby server 收到後直接回傳 
	`resp = {"type":"create_room_ok","detail":"room created"}`
3. show_profile
	從 userlist 抓取該使用者資料。
	回傳 `resp = {"type": "profile", "username" : , "win": , "total_game" : }`
4. logout
	將使用者登出。回傳 `resp =  {"type":"logout"}`
	更改使用者狀態 `lobby` -> `offline`
##### player_status == "waiting"
表示client 在 配對、創造房間 時的狀態。Lobby server 會收到兩種operation。
1. back
	表示client 取消配對，即將返回Lobby。
	直接回傳 `resp = {"type":"back","detail":"matching fail"}`
2. join_game
	client 完成配對，即將進入遊戲。
	回傳 `resp = {"type":"join_game", "detail":"join a game"}`
	更改使用者狀態 `lobby` -> `gaming`、`total_game` 增加 1。
##### player_status == "gaming"
表示 client 在遊戲中。Lobby server 會收到兩種operation。
1. check_connect
	Client 確認與Lobby server 的連線，直接回傳 `resp = {"type":"ACK", "detail": "Still Connect"}`
2. end_game
	Client 結束遊戲，彙報遊戲結果。
	回傳 `resp = {"type":"back", "detail": "end game and go back to the lobby."}`
	更改使用者狀態 `gaming` -> `lobby`，`win` 根據 msg 中 `"win"`欄位中夾帶的結果
#### Exception handling
1. Wrong Json format.
	退件，`resp = {"type": "error", "err": "bad_json", "detail": str(e)}`
2. Unknown player status
	直接將 msg 寄回去，回傳 `resp = {"type":"echo","recv":msg}` 。
3. Client disconnection
	如果 Client 已經登入過，將使用者狀態 `status` 修改成 `offine`。若沒登入，不處理。

## Client
### Overview
整體的架構是Finite State Machine。會根據目前的status 決定可以執行的操作以及顯示的頁面。
流程基本上是 寄送訊息 + 收訊息 一直重複直到terminate。
```python
while true:
	if player_status == "init":
		msg = init_page() ...
	elif player_status == "lobby":
	...
	send msg to server
	
	recv resp from server
	# 根據server response去 改變狀態
	if resp ...

```
這邊的status與server 那邊的 status儲存的狀態不太一樣，主要是在處理Client 內更細部的操作。
![[Pasted image 20251008131925.png]]
### helper function
#### Non-blocking input helper
為了使在等待連線時，可以輸入字詞離開
* poll_user_command : 持續的 readline，去捕捉使用者的輸入
* nb_input : 將使用者的輸入彙整起來
#### tool
與Lobby server那邊相同，傳輸的資料格式是Json，所以寫了sendjson, recv 等函式協助傳遞。

### Process Flow
#### Initially set up the connection with Lobby server
當運行程式的時候，會先與Lobby server建立TCP連線，等待接收歡迎訊息。
待TCP連線建立成功，收到歡迎訊息， _進入 init_
#### Route
##### init_page
當使用者狀態是 `init` 時，會進入這個頁面，使用者有三種操作可以選擇。
1. Register
	要求使用者輸入註冊的帳密，回傳 `msg = {"status": "init", "operation":"register", "username":user, "password":password}`
	Lobby server 會回覆 註冊成功與否。
	
2. Login
	要求使用者輸入註冊的帳密，回傳 `msg = {"status": "init", "operation":"login", "username":user, "password":password}`
	收到 Lobby server 回覆 登入成功時，使用者狀態會更改成 `lobby` -> _進入 lobby_
	
3. Exit
	直接回傳 `msg = {"status": "init", "operation":"exit"}`
	隨後斷絕連線，程式中止。 _End program_

##### Lobby
當使用者狀態是 `lobby` 時，會進入這個頁面，使用者有五種操作可以選擇。
1. Find an opponent
	回傳 `msg = {"status": "lobby", "operation":"match"}`
	收到 Lobby server 回覆後，使用者狀態會更改成 `matching` -> _進入match_
	
2. Create a room
	回傳 `msg = {"status": "lobby", "operation":"create_room"}`
	收到 Lobby server 回覆後，使用者狀態會更改成 `waiting` -> _進入waiting_
	
3. Learn rule
	印出規則，然後請使用者再操作一次。
	
4. Show profile
	回傳 `msg = {"status": "lobby", "operation":"show_profile"}`
	收到 Lobby server 回傳的資訊後，打印出來。
	
5. Logout
	回傳 `msg = {"status": "lobby", "operation":"logout"}`
	收到 Lobby server 回覆後，使用者狀態會更改成 `init` -> _返回 init_

##### match
當使用者的狀態是 `match` 時，會進入這個頁面。
首先會進行掃描工作：
```python
設立 UDP port 掃描 CSIT server # port range: (10299, 10499, ..., 12299) 寄送 FIND
若對方有回應 ACK，將 list.append((IPaddr, port))
最後將 list 印出供玩家選擇配對對象
```
接著使用者可以選擇其中一位玩家發送配對邀請，或是輸入 `leave` 離開配對（_返回 lobby_）
若對方`逾時`或是 `拒絕` (recv REJECT)，會將該玩家從名單中剃除，再請玩家輸入一次。
若對方 `接受` (recv ACCEPT) ，會設立一個 TCP socket 將自己的IPaddr, port 等資訊寄送給對方，邀請對方連線。

若連線成功，回傳 `msg = {"status": "waiting", "operation": "join_game", "other": "from match"}` 給 Lobby server，收到 Lobby server 的回覆後將使用者狀態更改成 `gaming` -> _進入 game_

若連線失敗，回傳 `msg = {"status": "waiting", "operation": "back"}` 給 Lobby server，收到回覆後將使用者狀態更改成 `lobby` -> _返回 lobby_

##### create_room
當使用者狀態是`waiting` 時，會進入這個頁面。
``` python
在 port_range 10699, 10899, ..., 12299 架設 UDP socket 等待邀請。
當收到別人寄送 FIND 的時候，會自主回應 ACK。
```
當收到別人的邀請訊息時，會請使用者輸入是否接受邀請 y/n/leave。
1. y -> Yes 接受邀請
	寄送 ACCEPT，等待對方的 TCP 連線資訊。
	成功連線後，向 Lobby server 回傳 `msg = {"status": "waiting", "operation": "join_game", "other":"from create"}` 
	收到 Lobby server 回傳後，更改使用者狀態成 `gaming` -> _進入 game_
	
2. n -> No 拒絕，繼續等待
	在等待時仍可輸入 leave 離開。
	
3. Leave 拒絕，直接離開等待
	回傳 `msg = {"status": "waiting", "operation": "back"}`
	收到 Lobby server 回傳後，更改使用者狀態成 `lobby` -> _返回lobby_

##### game
當使用者的狀態是 `gaming` 時，會進入這個遊戲頁面。由發起配對的人做先手，一來一回直到遊戲結束。當輪到使用者的回合時，按照上一次對手的行動更新畫面後，會請使用者輸入操作。
1. switch skill mode
	將使用者的技能模式切換 (use -> not; not -> use)
2. call a number
	請使用者輸入要呼叫的號碼
	傳遞本回合資訊給對手 `msg = {"call":num, "use_skill":self.use_skill_mode, "win":False, "end_game":False}`
3. quit
	離開遊戲
	`msg = {"call":num, "use_skill":self.use_skill_mode, "win":False, "end_game":True}`

結束後各自回傳遊戲結果給 Lobby Server
`msg = {"status":"gaming", "operation":"end_game", "win":self.win}`
當收到 Lobby server 回傳後，更改使用者狀態成 `lobby` -> _返回lobby_

# The Game Play : Shadow Bingo
## Game Rule
像是一般的Bingo遊戲，你需要在 5 X 5 的遊戲盤上達成 3 條連線。
當然，我們含有**技能**讓你干擾你的對手。
每個人皆有兩次技能使用機會，使用技能，能讓對手永遠沒辦法劃掉那一個數字。
如何在遊戲中靠運氣、實力獲勝，請來玩玩看 Shadow Bingo。
## Game Flow
遊戲內資料傳輸可以參考：[[#game]]
當遊戲開始時，由當初發起match的人作為先手 (player A)。

1. 產生自己的遊戲盤
2. A 決定使用技能與否、叫號
3. 更新 A 地圖
4. 判斷 A 是否勝利 (若勝利則跳出)
5. 傳送資料給 B
6. B 按照資料更新地圖
7. go to step2, but now A is B, B is A.