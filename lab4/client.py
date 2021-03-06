import socket
import sys
import time
import boto3
import os
from kafka import KafkaConsumer
import sqlite3
import threading

s3 = boto3.resource('s3')
target_bucket = None
uid = -1
t = None
consumer = None
stop_flag = False

def consume(consumer):
	global stop_flag
	conn = sqlite3.connect('Database.db')
	c = conn.cursor()
	while True:		
		msg = consumer.poll(timeout_ms = 500) ## fetch in 0.5sec
		if msg:
			time.sleep(0.3)			
			for value in msg.values():				
				for record in value:
					print_flag = False
					topic = record[0] ## board or author
					post_id = record[6].decode('utf-8')
					sql_return_post = c.execute('select * from POST where ID = ?', (post_id,)).fetchone()
					board = c.execute('select Name from BOARD where ID = ?',(sql_return_post[4],)).fetchone()[0]
					author = c.execute('select Username from USERS where UID = ?', (sql_return_post[2],)).fetchone()[0]
					
					keyword_board = c.execute('select Keyword from Sub_BOARD where Board_name = ? and Subscriber_id = ?', (topic, uid))
					for row in keyword_board:
						if row[0] in sql_return_post[1] and not print_flag: # keyword in title or not
							print('*[{}]{} - by {}*\r\n% '.format(board, sql_return_post[1], author), end = '')
							print_flag = True
					keyword_author = c.execute('select Keyword from Sub_AUTHOR where Author_name = ? and Subscriber_id = ?', (topic, uid))
					for row in keyword_author:
						if row[0] in sql_return_post[1] and not print_flag:
							print('*[{}]{} - by {}*\r\n% '.format(board, sql_return_post[1], author), end = '')
							print_flag = True
			
		if stop_flag == True:
			break 

def mkdir():
    Pdata = "./.data"
    Ppost = "./.data/post"
    Pcomment = "./.data/comment"
    Pmail = "./.data/mail"
    try:
    	os.makedirs(Pdata)
    except FileExistsError:
    	pass
    try:
    	os.makedirs(Ppost)
    except FileExistsError:
    	pass
    try:
    	os.makedirs(Pcomment)
    except FileExistsError:
    	pass
    try:
    	os.makedirs(Pmail)
    except FileExistsError:
    	pass

def receive(len):
	while True:
		try:
			msg_in = s.recv(len).decode('utf-8')
			return msg_in
		except:
			pass

def Subscribe(msg_in):
	msg_in_split = msg_in.split('###')
	topic = []
	sql_return = c.execute('select Board_name from SUB_BOARD where Subscriber_id = ?', (uid,))
	for row in sql_return:
		topic.append(row[0])
	sql_return = c.execute('select Author_name from SUB_AUTHOR where Subscriber_id = ?', (uid,))
	for row in sql_return:
		topic.append(row[0])
	consumer.subscribe(topics=(topic))
	msg_in = msg_in_split[0]
	return msg_in

def DeleteMail(msg_in):
	msg_in_split = msg_in.split('###')
	mail_id_in_db = msg_in_split[1]

	os.remove("./.data/mail/m{}.txt".format(mail_id_in_db))
	target_bucket.Object("m{}.txt".format(mail_id_in_db)).delete()

	msg_in = msg_in_split[0]
	return msg_in

def RetrMail(msg_in):
	msg_in_split = msg_in.split('###')
	tmp_bucket = s3.Bucket(msg_in_split[2])
	mail_id_in_db = msg_in_split[1]
	print(msg_in_split[0])

	target_object = tmp_bucket.Object("m{}.txt".format(mail_id_in_db))
	object_content = target_object.get()['Body'].read().decode()
	print('    --')
	object_content_list = object_content.split('<br>')
	for i in object_content_list:
		print('    {}'.format(i))

	msg_in = ""
	return msg_in

def SendMail(cmd_list, msg_in):
	msg_in_split = msg_in.split('###')
	content_position = cmd_list.index('--content')
	content = ' '.join(cmd_list[content_position+1:len(cmd_list)])
	mail_id = msg_in_split[1]
	fp = open("./.data/mail/m{}.txt".format(mail_id), "w")
	fp.write(content)
	fp.close()
	tmp_bucket = s3.Bucket(msg_in_split[2])
	tmp_bucket.upload_file("./.data/mail/m{}.txt".format(mail_id), "m{}.txt".format(mail_id))
	return  msg_in_split[0]


def Comment(cmd_list, msg_in):
	msg_in_split = msg_in.split('###')
	name = msg_in_split[2]
	comment = ' '.join(cmd_list[2:len(cmd_list)])
	fp = open("./.data/comment/c{}.txt".format(cmd_list[1]), "a")
	fp.write('    {}:{}\n'.format(name, comment))
	fp.close()

	tmp_bucket = s3.Bucket(msg_in_split[1])
	tmp_bucket.upload_file("./.data/comment/c{}.txt".format(cmd_list[1]), "c{}.txt".format(cmd_list[1]))
	
	return msg_in_split[0]

def UpdatePost(cmd_list, msg_in):
	update_data = ' '.join(cmd_list[3:len(cmd_list)])
	fp = open("./.data/post/p{}.txt".format(cmd_list[1]), "w")
	fp.write(update_data)
	fp.close()
	target_bucket.upload_file("./.data/post/p{}.txt".format(cmd_list[1]), "p{}.txt".format(cmd_list[1]))

def ReadPost(cmd_list, msg_in):
	msg_in_split = msg_in.split('###')
	tmp_bucket = s3.Bucket(msg_in_split[1])
	print(msg_in_split[0])

	target_object1 = tmp_bucket.Object("p{}.txt".format(cmd_list[1]))
	object_content = target_object1.get()['Body'].read().decode()
	target_object2 = tmp_bucket.Object("c{}.txt".format(cmd_list[1]))
	object_comment = target_object2.get()['Body'].read().decode()

	print('    --')
	object_content_list = object_content.split('<br>')
	for i in object_content_list:
		print('    {}'.format(i))
	print('    --')
	print(object_comment, end='')
	msg_in = ""
	return msg_in

def DeletePost(cmd_list):
	os.remove("./.data/post/p{}.txt".format(cmd_list[1]))
	os.remove("./.data/comment/c{}.txt".format(cmd_list[1]))
	target_bucket.Object("p{}.txt".format(cmd_list[1])).delete()
	target_bucket.Object("c{}.txt".format(cmd_list[1])).delete()

def CreatePost(cmd_list, msg_in):
	post_id = msg_in.split('###')[1]
	content_position = cmd_list.index('--content')
	content = ' '.join(cmd_list[content_position+1:len(cmd_list)])

	fp = open("./.data/post/p{}.txt".format(post_id), "w")
	fp.write(content)
	fp.close()
	fp = open("./.data/comment/c{}.txt".format(post_id), "w")
	fp.close()
	target_bucket.upload_file("./.data/post/p{}.txt".format(post_id), "p{}.txt".format(post_id))
	target_bucket.upload_file("./.data/comment/c{}.txt".format(post_id), "c{}.txt".format(post_id))
	msg_in = msg_in.split('###')[0]
	return msg_in

def command(cmd_list, msg_in, s, target_bucket):
	global t, consumer, uid, stop_flag
	if msg_in == 'Register successfully.\r\n':
		bucket_name = '0516319-' + cmd_list[1] + '-0516319'		
		s3.create_bucket(Bucket = bucket_name)
	elif cmd_list[0] == 'login' and msg_in.startswith('Welcome, '):
		bucket_name = msg_in.split('###')[1]
		target_bucket = s3.Bucket(bucket_name)
		user_name = msg_in.split('-')[1]
		msg_in = msg_in.split('###')[0]		

		sql_return = c.execute('select UID from USERS where Username = ?', (user_name,)).fetchone()
		uid = sql_return[0]
		user_name = user_name + '-' + str(time.time())
		consumer = KafkaConsumer(group_id = user_name, bootstrap_servers=['127.0.0.1:9092'])
		t = threading.Thread(target = consume, args = (consumer,))
		t.start()
		stop_flag = False
	elif cmd_list[0] == 'logout' and msg_in.startswith('Bye'):
		c.execute('delete from SUB_BOARD where Subscriber_id = ?', (uid,))
		c.execute('delete from SUB_AUTHOR where Subscriber_id = ?', (uid,))
		conn.commit()
		target_bucket = None		
		stop_flag = True		
		consumer = None
		uid = -1
	elif cmd_list[0] == 'create-post' and msg_in.startswith('Create post successfully'):
		msg_in = CreatePost(cmd_list, msg_in)		
	elif cmd_list[0] == 'delete-post' and msg_in == 'Delete successfully.\r\n':
		DeletePost(cmd_list)
	elif cmd_list[0] == 'read' and not (msg_in == 'Post does not exist.\r\n' or msg_in == 'Usage: read <post-id> \r\n'):
		msg_in = ReadPost(cmd_list, msg_in)
	elif cmd_list[0] == 'update-post' and msg_in == 'Update successfully.\r\n':
		UpdatePost(cmd_list, msg_in)
	elif cmd_list[0] == 'comment' and msg_in.startswith('Comment successfully'):
		msg_in = Comment(cmd_list, msg_in)
	elif cmd_list[0] == 'mail-to' and msg_in.startswith('Sent successfully'):
		msg_in = SendMail(cmd_list, msg_in)	
	elif cmd_list[0] == 'retr-mail' and msg_in.endswith('0516319'):
		msg_in = RetrMail(msg_in)
	elif cmd_list[0] == 'delete-mail' and msg_in.startswith('Mail deleted'):
		msg_in = DeleteMail(msg_in)	
	elif cmd_list[0] == 'subscribe' and msg_in.startswith('Subscribe successfully'):
		msg_in = Subscribe(msg_in)
	else:
		pass
	return msg_in, target_bucket


dst_ip = str(sys.argv[1])
port = int(sys.argv[2])
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect((dst_ip, port))
msg_in = s.recv(1024).decode('utf-8')
print(msg_in,end = "")
s.setblocking(0)
mkdir()
conn = sqlite3.connect('Database.db')
c = conn.cursor()

while True:
	cmd = input("% ")
	cmd_list = cmd.split()
	if not cmd or len(cmd_list) == 0:
		pass
	elif cmd_list[0] == "exit":
		if uid != -1:
			c.execute('delete from SUB_BOARD where Subscriber_id = ?', (uid,))
			c.execute('delete from SUB_AUTHOR where Subscriber_id = ?', (uid,))
			conn.commit()
		stop_flag = True
		s.send(cmd.encode('utf-8'))
		sys.exit()
	else:
		s.send(cmd.encode('utf-8'))
		msg_in = receive(8192);
		msg_in, target_bucket = command(cmd_list, msg_in, s, target_bucket)
		if msg_in != "":
			print(msg_in ,end = "")
