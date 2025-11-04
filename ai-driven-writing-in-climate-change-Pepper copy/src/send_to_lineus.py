#!/usr/bin/env python3
"""
发送G代码到LineUs机器人
"""

import socket
import time
import sys


class LineUsSender:
    def __init__(self, hostname='line-us.local', port=1337):
        self.hostname = hostname
        self.port = port
        self.sock = None
    
    def connect(self):
        """连接到LineUs"""
        print(f"连接到 {self.hostname}:{self.port}...")
        
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(10)
            self.sock.connect((self.hostname, self.port))
            
            # 读取hello消息
            response = self.sock.recv(1024).decode('utf-8')
            print(f"收到: {response.strip()}")
            
            if 'hello' in response:
                print("✓ 连接成功!")
                return True
            else:
                print("✗ 未收到hello消息")
                return False
                
        except Exception as e:
            print(f"✗ 连接失败: {e}")
            return False
    
    def send_gcode(self, gcode_line):
        """发送单行G代码"""
        try:
            # 发送命令
            command = gcode_line.strip() + '\n'
            self.sock.sendall(command.encode('utf-8'))
            
            # 读取响应
            response = self.sock.recv(1024).decode('utf-8')
            
            if 'ok' in response:
                return True
            else:
                print(f"  警告: {response.strip()}")
                return False
                
        except Exception as e:
            print(f"  错误: {e}")
            return False
    
    def send_file(self, gcode_file, delay=0.05):
        """发送整个G代码文件"""
        print(f"\n读取G代码文件: {gcode_file}")
        
        with open(gcode_file, 'r') as f:
            lines = f.readlines()
        
        print(f"共 {len(lines)} 行")
        print("\n开始绘图...")
        
        sent = 0
        for i, line in enumerate(lines, 1):
            line = line.strip()
            
            # 跳过空行和注释
            if not line or line.startswith(';'):
                continue
            
            # 显示进度
            if sent % 10 == 0:
                print(f"  进度: {sent}/{len(lines)} ({i}/{len(lines)}行)", end='\r')
            
            # 发送G代码
            if self.send_gcode(line):
                sent += 1
                time.sleep(delay)  # 延迟避免过快
            else:
                print(f"\n第{i}行发送失败: {line}")
        
        print(f"\n✓ 完成! 发送了 {sent} 条G代码命令")
    
    def close(self):
        """关闭连接"""
        if self.sock:
            self.sock.close()
            print("连接已关闭")


def main():
    if len(sys.argv) < 2:
        print("用法: python send_to_lineus.py <gcode文件> [hostname]")
        print("\n使用默认文件...")
        gcode_file = "/mnt/user-data/outputs/lineus_output.gcode"
    else:
        gcode_file = sys.argv[1]
    
    hostname = sys.argv[2] if len(sys.argv) > 2 else 'line-us.local'
    
    sender = LineUsSender(hostname=hostname)
    
    try:
        if sender.connect():
            sender.send_file(gcode_file)
    except KeyboardInterrupt:
        print("\n\n中断发送")
    finally:
        sender.close()


if __name__ == "__main__":
    main()
