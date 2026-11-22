PORT ?= 4003
MPREMOTE = mpremote connect port:rfc2217://localhost:$(PORT)

.PHONY: deploy

bootstrap:
	mpremote fs cp secrets.py :secrets.py
	mpremote mip install github:its-the-vibe/TinyUpdater/updater.py
	mpremote mip install github:peterhinch/micropython-touch
	mpremote run bootstrap.py

deploy:
	mpremote fs cp main.py :main.py
	mpremote fs cp secrets.py :secrets.py
	mpremote fs cp touch_setup.py :touch_setup.py
	mpremote fs cp ili9486_16bit.py :ili9486_16bit.py
	mpremote fs cp wifi.py :wifi.py
	mpremote run main.py

dev:
	$(MPREMOTE) run main.py
