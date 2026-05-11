from setuptools import find_packages, setup

package_name = 'ros2_glove'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', ['launch/glove.launch.py']),
    ],
    install_requires=['setuptools', 'pyserial'],
    zip_safe=True,
    maintainer='Bogdan',
    maintainer_email='bcostea1@gmail.com',
    description='ROS 2 Humble driver for the ESP32 smart glove',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'glove_driver = ros2_glove.glove_driver_node:main',
        ],
    },
)
