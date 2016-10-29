# CurtainControl
Node.js control of Somfy SDN curtains and keypads

1) log into the raspberry pi with putty
2) install node.js into raspberry pi
	>wget http://node-arm.herokuapp.com/node_latest_armhf.deb 
	>sudo dpkg -i node_latest_armhf.deb
3) copy node project to raspberry pi with winscp
4) execute project with debugger
	>nodejs RemoteDebug.js server.js
5) execute project
	>nodejs server.js


Notes:
Set timezone: >sudo dpkg-reconfigure tzdata
Reboot: >sudo reboot
