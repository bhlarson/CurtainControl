# CurtainControl?Node.js control of Somfy SDN curtains and keypads??
1) log into the raspberry pi with putty?
2) install node.js into raspberry pi?	
	>wget http://node-arm.herokuapp.com/node_latest_armhf.deb
	>sudo dpkg -i node_latest_armhf.deb
3) copy node project to raspberry pi path "/home/pi/CurtainControl" with winscp
3  alt) sync project from git:
# create source code archive  
> git clone https://github.com/bhlarson/CurtainControl.git  
> cd CurtainControl
# sync with github repository after archive created  
> git pull origin master
# update dependencies  
> nmp update
#  install and build serialport
> npm install serialport --unsafe-perm --build-from-source  
4) execute project with debugger
>node RemoteDebug.js server.js
5) execute project
>node server.js
6) auto start:?	
	a) Log into to pi as root in putty?
	b) Copy  �nodecurtain.service� to /etc/system/system	
	c) Enable and start:
		$  sudo systemctl enable nodecurtain.service
		$  sudo systemctl restart nodecurtain.service
		$  sudo systemctl disable nodecurtain.service
		$ ps aux
7) Console out logged to "/var/log/syslog" startup logged to "/var/log/messages"??Create mysql datbase:????

Notes: Set timezone: >sudo dpkg-reconfigure tzdata?Reboot: >sudo reboot
>ps <- list running processes
> pidof node  <-  node process id
