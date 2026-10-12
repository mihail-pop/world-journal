# Remote Access

World Journal currently supports local use on the computer running Django. The setup guides bind the server to `127.0.0.1`, which keeps it unavailable to other devices by default.

## Trusted Local Networks

Django can be bound to a LAN address, but World Journal has no accounts and uses plain HTTP by default. Anyone who can reach that address can access and modify all shared data.

I do not recommend changing the bind address unless every device and person on that network is trusted. Firewall rules, host configuration and HTTPS are the responsibility of the person running the server.

## Public Internet

Do not forward the port, bind it publicly or place it behind a public tunnel. The app currently has:

- no login requirement;
- no separation between users;
- a development secret key;
- debug mode enabled;
- no documented production web server or reverse proxy configuration.

Remote hosting needs a dedicated security and deployment pass. This page is ready for those instructions later, but public access is not supported now.
