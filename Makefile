install-dependencies:
	apt install influxdb bluez python3-pip libsystemd-dev
	pip3 install -r requirements.txt
install-services:
	cp systemd/* /etc/systemd/system/
	systemctl daemon-reload
	systemctl enable esc-bms.service esc-inverter-controller.service esc-charge-controller.service
