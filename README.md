# CurtainControl?Node.js control of Somfy SDN curtains and keypads
- Install raspban linux on raspberry pi: https://www.raspberrypi.org/downloads/raspbian/
- http://thisdavej.com/beginners-guide-to-installing-node-js-on-a-raspberry-pi/
- Update linux:
> sudo apt-get update
> sudo apt-get dist-upgrade
- Install FTDI USB serial  driver
> wget http://www.ftdichip.com/Drivers/D2XX/Linux/libftd2xx-arm-v7-hf-1.3.6.tgz
> gunzip lib*
> tar -vf lib*
> sudo cp ./release/build/lib* /usr/local/lib
> cd /usr/local/lib 
>  sudo ln �s libftd2xx.so.1.3.6 libftd2xx.so
> sudo chmod 0755 libftd2xx.so.1.3.6
> enable SSH from sudo raspi-config interface options
1) log into the raspberry pi with putty
2) install node.js into raspberry pi?	
> curl -sL https://deb.nodesource.com/setup_7.x | sudo -E bash -
> sudo apt install nodejs
	>wget http://node-arm.herokuapp.com/node_latest_armhf.deb
	>sudo dpkg -i node_latest_armhf.deb
	> node -v
3) copy node project to raspberry pi path "/home/pi/CurtainControl" with winscp
3  alt) sync project from git:
> git clone https://github.com/bhlarson/CurtainControl.git  <- create source code archive
> cd CurtainControl
> git pull origin master <- sync with github repository after archive created
> nmp update <- update dependencies
> sudo npm install serialport --unsafe-perm --build-from-source <-  install and build serialport
4) execute project with debugger
>nodejs RemoteDebug.js server.js
5) execute project
>nodejs server.js
6) auto start:?	
	a) Log into to pi as root in putty?
	b) Copy  �nodecurtain.service� to /etc/system/system	
	c) Enable and start:
		$  sudo systemctl enable nodecurtain.service
		$  sudo systemctl restart nodecurtain.service
		$  sudo systemctl disable nodecurtain.service
		$ ps aux
7) Console out logged to "/var/log/syslog" startup logged to "/var/log/messages"??Create mysql datbase:????

Notes: 
Set timezone: 
>sudo dpkg-reconfigure tzdata
Reboot: >sudo reboot
>ps <- list running processes
> pidof node  <-  node process id
