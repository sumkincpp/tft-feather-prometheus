WINDOWS_PATH = 'D:\'
LINUX_PATH = '/mnt/d/'

hello:
	@echo "Hello, World!"
	@echo "It's the good thing to have empty default target."

copy_windows:
	cp -v *.py bmeTFT.bmp roundedHeavy-26.bdf $(WINDOWS_PATH)

copy:
	cp -v *.py bmeTFT.bmp roundedHeavy-26.bdf $(LINUX_PATH)
