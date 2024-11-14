Gossip Module for Anonymous and Unobservable VoIP Application, for the course Peer-to-Peer Systems and Security (IN2194) at TUM SoSe 2023

Running The Program:

- Follow the following steps to run the program without docker:

1. Make sure you have python 3.9 or above installed on your machine
2. Run the following command from the main directory of the project to install the required dependencies:
   python3 -m pip install -r requirements.txt
3. Run the following command to start the program (the -c argument is optional and will default to config.ini):
   python3 run.py -c config.ini
4. You can run multiple nodes on different terminals with different config files that have different api and p2p addresses/ports.

- Follow the following steps to run multiple nodes of the program with docker compose:

1. Make sure you have docker installed on your machine
2. (Optional) Edit the docker-compose.yml if needed to add/remove nodes or to change their config file path (through environment -> conf). Make sure the ports and ipv4 address matches the config files.
3. Run the following command to build a docker image (should be run every time config files are modified):
   docker build -t peer .
4. Run the following command to start docker compose using the image created:
   docker-compose up
