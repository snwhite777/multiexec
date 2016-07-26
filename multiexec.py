'''
This python script's main objective is to deploy command to a list of destination hosts
  simulatenously using Python multiprocessing module. The script will be hosted in the 
  admin host aka jumpbox aka sysadmin server from where system admins login to the rest of 
  the servers in the infrastructure.

This script works in 2 following assumptions:
1. The admin host that hosts this script can log in passwordlessly to all destination 
  hosts in the list (using SSH key).
2. Python34 package (http://ftp.riken.jp/Linux/fedora/epel/7/x86_64/p/python34-3.4.3-4.el7.x86_64.rpm)
  and Paramiko(www.paramiko.org/installing.html) are required for this script to work.

Some guideline to install Paramiko for python3:
- install python-devel (yum -y install python34-devel)
- install pip (python3 /usr/lib/python3.4/site-packages/easy_install.py pip)
- use pip3 to install cryptography (pip3 install cryptography)
- use pip3 to install paramiko (pip3 install paramiko)

To display usage, type python3 multiexec.py --help

Below modules are imported into this script:
  argparse - to parse script parameters and print script --help message
  functools - to use partial for parsing function into multiprocessing Pool imap function
  multiprocessing - to provide multiprocess features (in order to log in to multiple 
    hosts simultaneously)
  os - to create output directory (where to result of command deployed can be found)
  paramiko - to implement SSH features (remote execution and SCP files)

In this script, the variable/parameters will be quoted, for example, variable hostname will
  be written as "hostname"
'''

import argparse
from functools import partial
from multiprocessing import Pool,TimeoutError
from multiprocessing.dummy import Pool as ThreadPool
import os
import paramiko as pr

__author__ = "Nam Tran"
__copyright__ = "Copyright 2016"
__email__ = "namtt.7@gmail.com"

def execute(host,out_dir,filename,command):
	"""
	The execute function helps to deploy command stored in "command"
	  parameter to 1 destination host, the destination hostname is stored in the "host" parameter
	
	Parameters of the function:
	host - hostname of the destination host
	out_dir - the directory where command execution output is stored. The file where
	  output is stored is "out_dir"/"host"
	filename - the file that will be SCPed to destination host. The file will be
	  put in /var/tmp/ directory in the destination host
	command - the command that will be executed in the destination host
	"""

	#- Initiate the SSHClient instance and connect to the destination host
	#- AutoAddPolicy is set so that the destination host do not need to be
	#in the known_hosts file of the admin
	#- load_system_host_keys load the host keys from default location ~user/.ssh/known_hosts
	#- Adding try - exception to catch errors
	try:
		ssh_client = pr.SSHClient();
		ssh_client.set_missing_host_key_policy(pr.AutoAddPolicy());
		ssh_client.load_system_host_keys();
		ssh_client.connect(host);
	except:
		return "Unable to connect to {}".format(host);

	#- SCP to /var/tmp in the destination host if "filename" option is specified
	#- SFTPClient documentation is at http://docs.paramiko.org/en/2.0/api/sftp.html
	if filename != None:
		sftp_session = ssh_client.open_sftp();
		path,name = os.path.split(filename);
		sftp_session.put(filename,"/var/tmp/{}".format(name));
		sftp_session.close();
	
	#- Execute the command in the destination host using SSHClient method exec_command
	#- Documentation of SSHClient is at http://docs.paramiko.org/en/2.0/api/client.html
	#- Write the command output to "out_dir"/"host" directory
	stdin, stdout, stderr = ssh_client.exec_command(command);
	stdin.close()
	result = stdout.read().decode();
	if not os.path.exists(out_dir):
		os.makedirs(out_dir);
	file = open("{}/{}".format(out_dir,host),'w');
	file.write(result);
	file.close();
	return result;

def abortable_func(func, *args, **kwargs):
	"""
	The abortable_func is the wrapper function, which wraps around function type "func", call 
	  it in a background thread (multiprocessing.dummy.Thread), and terminates it after
	  "timeout" seconds.
	This function is inspired by 
	  http://stackoverflow.com/questions/29494001/how-can-i-abort-a-task-in-a-multiprocessing-pool-after-a-timeout
	  but is an improvement over the original solution, since the original solution is only 
	  applicable to a function that takes positional arguments.

	Parameters of the function:
	  func - the function that will be called and terminated if not return with "timeout" seconds
	  *args - positional arguments of "func"
	  **kwargs - named arguments of "func" + "timeout" value
	"""
	
	#- Get "timeout" value and create a ThreadPool (multiprocessing.dummy.Pool) 
	#  with only 1 worker. 
	#- Use functools.partial (https://docs.python.org/3/library/functools.html)
	#  to fit all the arguments of the func into the interface of
	#  Pool.apply_async function
	timeout = kwargs.pop('timeout', None);
	p = ThreadPool(1);
	partial_func = partial(func,**kwargs);
	res = p.apply_async(partial_func,args);

	#- Terminate the thread if it does not return after "timeout" seconds
	#  otherwise return the returned value of func
	try:
		out = res.get(timeout);
		return out
	except TimeoutError:
		p.terminate()
		return "Timeout exceeded. Process terminated.";

def main():
	"""
	The main function will process the paramters parsed to the script. Type python3 multiexec.py --help to get usage of this script
	This function also spawned the child processes to execute command to multiple destination hosts at once.
	"""
	#Parsing the arguments of the script using argparse. Documentation of argparse can be found at
	#  https://docs.python.org/3/library/argparse.html
	parser = argparse.ArgumentParser(description="This script is used to deploy command to a large list of servers using multiprocessing");
	parser.add_argument('--hostlist', help='File that contains the destination hostnames. Example is ./hostlist.txt.', type=str, required=True);
	parser.add_argument('--command', help='Command to be executed in the destination hosts',type=str,required=True);
	parser.add_argument('--timeout', help='Number of seconds before a child process is terminated',type=int,default=60);
	parser.add_argument('--out_dir', help='Directory where the command output is stored',type=str,required=False,default='/tmp/OUT');
	parser.add_argument('--max_child', help='Maximum number of child processes being spawned at once',type=int,default=5);
	parser.add_argument('--filename', help='(OPTIONAL)The file will be copied to all destination hosts at /var/tmp/',required=False);
	args = parser.parse_args();
	#... parsing hostlist and command
	hostlist = open(args.hostlist,'r');
	hosts = hostlist.read().splitlines();
	command = args.command;
	
	#...timeout
	timeout = args.timeout;

	#...out_dir
	if args.out_dir != '':
		out_dir = args.out_dir;
	else:
		out_dir = '/tmp/OUT';
	#...max_child
	if args.max_child > len(hosts):
		max_child = len(hosts);
	else:
		max_child = args.max_child;	
	
	#...filename
	if args.filename != '':
		filename = args.filename;
	else:
		filename = '';
	partial_execute = partial(abortable_func, execute, timeout=timeout,command=command,filename=filename,out_dir=out_dir);		
	
	
	#Create the worker pool and depoy the command to all destination hosts
	p = Pool(max_child);
	print("Output are printed to {}".format(out_dir));
	for i in p.imap(partial_execute,hosts,1):
		if i=="Timeout exceeded. Process terminated.":
			print(i);

if __name__ == "__main__":
	main()

	
