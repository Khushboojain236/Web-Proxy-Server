import socket
import threading
import sys
from cmd import Cmd
import select
import time
import os
from urllib.request import Request, urlopen, HTTPError

#constants 
# alot of the code is based on geeksforgeeks tutorial
BIND_PORT=8076
SOCKET_IP='localhost'
HTTPS_BUFFER = 8192
HTTP_BUFFER = 4096

MAX_CONNECTIONS = 600
active_connections = 0

#cache list
cache={}  
#blocked list
blocked_list= set([])
response_times={}

prev_blocked_list=[]

class input_cmd(Cmd):
    prompt = ">>"
    def do_help(self,args):
        print("Enter `block` followed by URL to block (block www.google.com)")
        print("Enter `blockedlist` see a blocked list")
        print("To quit proxy, enter `quit`")
    
    def do_block(self,args):
        try:
            input_url=args.rsplit(" ",1)
            input_url=input_url[0]
        except Exception as error:
            print("Please enter a valid URL")
        if not "www." in input_url:
            input_url = "www." + input_url
        #Adding to the block list
        blocked_list.add(input_url)
        #Adding to print list
        if input_url not in blocked_list and len(prev_blocked_list) < 10 :
            prev_blocked_list.append(input_url)
            
        #Printing the blocked URL    
        print("Blocked : ", input_url)
    
    def do_blockedlist(self,args):
        if blocked_list == []:
            print("There is nothing blocked")
        else:
            print(f"LIST OF BLOCKED URLs : {blocked_list}")
            
    def do_quit(self,args):
        print("Exiting...")
        raise KeyboardInterrupt()
    
    
    
    
def user_help_method(console, irr):
    console.cmdloop("Enter URL to be blocked: (eg - block www.google.com) or help to see available commands.")  
    
def main():
    console = input_cmd()
    
    #Multi-thread system 
    d=threading.Thread(target= user_help_method , args= (console, None))
    d.start()
    
    try:
        serverSocket=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        serverSocket.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        serverSocket.bind((SOCKET_IP,BIND_PORT))
        serverSocket.listen(MAX_CONNECTIONS)
    except Exception as error:
        print(f"Error in start method {error}")
        sys.exit(2) 
    
    global active_connections
    while active_connections<=MAX_CONNECTIONS:
        try:
            #accept connection from browsers
            conn, addr = serverSocket.accept()
            active_connections+=1
            thread=threading.Thread(name=addr,target=proxy_connect,args=(conn,addr))
            thread.setDaemon(True)
            thread.start()
        except KeyboardInterrupt:
            serverSocket.close()
            sys.exit(1)

def proxy_connect(conn,addr):
    global active_connections
    
    #receiving data from browser
    data=conn.recv(HTTP_BUFFER)
    
    if len(data)>0:
        try:
            request=data.decode().split('\n')[0]
            try:
                method=request.split(' ')[0]
                url=request.split(' ')[1]
                if method == 'CONNECT':
                    type='https'
                else:
                    type='http'
                
                if check_block_list(url):
                    active_connections-=1
                    print("Request denied as its blocked!")
                    conn.close()
                    return 
                #URL is not blocked
                else:
                    print("Request: " + request)
                    log("Request: " + request)
                    webserver = ""
                    port = -1
                    temp = parseURL(url,type)
                    
                    if len(temp)>0:
                        webserver, port = temp
                    else:
                        return
                    print("Connected to " + webserver + " on port " + str(port))
                    
                    start_time=time.time()
                    t= cache.get(webserver)
                    
                    if t is not None:
                        print("Send cached response")
                        conn.sendall(t)
                        finish_time=time.time()
                        print(f"Request took: {finish_time - start_time:0.2f} seconds with cache")
                        log(f"Request took: {finish_time - start_time:0.2f} seconds with cache")
                        print("Request took: "+ str(response_times[webserver]) + "s without cache.")
                        log(f"Request took: "+ str(response_times[webserver]) + "s without cache.")
                    
                    else:
                        serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        if type =='http':
                            if handle_http_request(serverSocket, webserver, port, data, conn) is True:
                                active_connections -= 1
                        elif type == 'https':
                            serverSocket.connect((webserver, port))
                            conn.send(bytes("HTTP/1.1 200 Connection Established\r\n\r\n", "utf8"))
                            connections = [conn, serverSocket]
                            
                            connected=True
                            while connected:
                                ready_sockets, sockets_for_writing, error_sockets = select.select(connections, [], connections, 600)
                                if error_sockets:
                                    break
                                
                                for ready_sock in ready_sockets:
                                    other=connections[1] if ready_sock is connections[0] else connections[0]
                                try:     
                                    data = ready_sock.recv(HTTPS_BUFFER)
                                except socket.error:
                                   ready_sock.close()
                                   
                                if data:
                                    other.sendall(data)
                                    connected=True
                                else:
                                    connected=False
            except IndexError:
                pass
        except UnicodeDecodeError:
            pass
    else:
        pass
      
def parseURL(url, type):
    http_position = url.find("://")

    # If "://" is not present then the temp is the url
    if (http_position == -1):
        tmp = url
    else:    
        tmp = url[(http_position+3):]
        
    # get port position and server from the Request
    port_position = tmp.find(":")
    webserver_position = tmp.find("/")

    if webserver_position == -1:
        webserver_position = len(tmp)

    webserver = ""
    port = -1

    #DEFAULT PORT
    if port_position == -1 or webserver_position < port_position:
        if type == "https":
            port = 443
        else:
            port = 80
        
        webserver = tmp[:webserver_position]
	# defined port
    else:												
        port = int((tmp[(port_position+1):])[:webserver_position-port_position-1])
        webserver = tmp[:port_position]

    return [webserver, int(port)]

def check_block_list(url):
    for temp_url in blocked_list:
        if temp_url in url:
            print(f"{url} is blocked")
            return True
    return False

def log(input):
    
    newFile = "/Users/vishal/log.txt"
    file = open(newFile, "a")
    file.write("\n" + input)
    file.flush()

def handle_http_request(serverSocket, webserver, port, data, conn):
    start_time=time.time()
    #for cache_set
    string_builder = bytearray("", 'utf-8')
    
    serverSocket.connect((webserver, port))
     # send client request to server
    serverSocket.send(data)
    serverSocket.settimeout(2)
    try:
        while True:
            webserver_data = serverSocket.recv(HTTP_BUFFER)
            if len(webserver_data) > 0:
                conn.send(webserver_data)
                string_builder.extend(webserver_data)
            else:
                break
    except socket.error:
        pass
    finish_time = time.time()
    print("Request took: " + str(finish_time-start_time))
    log("Request took: " + str(finish_time-start_time))
    response_times[webserver] = finish_time - start_time 
    cache[webserver] = string_builder
    print("Added to cache: " + webserver)
    log("Added to cache: " + webserver)
    serverSocket.close()
    conn.close()
    return True


main()