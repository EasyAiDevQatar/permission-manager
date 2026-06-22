from setuptools import find_packages, setup

from permission_manager import __version__


setup(
	name="permission_manager",
	version=__version__,
	description="Duplicate ERPNext roles with their complete effective permission matrix",
	author="EasyAiDevQatar",
	author_email="dev@easyaidev.com",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=[],
)
