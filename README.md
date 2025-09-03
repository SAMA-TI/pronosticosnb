# Streamlit App Production Deployment Guide

This guide documents the complete process to deploy a Streamlit application in production using Nginx as a reverse proxy on Fedora Linux.

## Prerequisites

- Fedora Linux server
- Python 3.x with venv
- Streamlit application ready to deploy

## Step 1: Python Environment Setup

### Create and activate virtual environment:

```bash
cd /path/to/your/project
python3 -m venv .venv
source .venv/bin/activate
```

### Install dependencies:

```bash
pip install -r requirements.txt
```

## Step 2: Streamlit Configuration

### Run Streamlit on all interfaces (not just localhost):

```bash
streamlit run streamlit_app.py --server.address 0.0.0.0 --server.port 8501
```

**Important**: Use `0.0.0.0` instead of `127.0.0.1` to make it accessible from other interfaces.

### For production, run as background process:

```bash
nohup streamlit run streamlit_app.py --server.address 0.0.0.0 --server.port 8501 > streamlit.log 2>&1 &
```

## Step 3: Nginx Installation and Configuration

### Install Nginx:

```bash
sudo dnf install nginx
sudo systemctl start nginx
sudo systemctl enable nginx
```

### Create Nginx configuration for Streamlit:

Create `/etc/nginx/conf.d/streamlit.conf`:

```nginx
server {
    listen 8080;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        proxy_read_timeout 86400;
    }
}
```

**Note**: Using port 8080 instead of 80 to avoid ISP blocking common ports.

### Remove conflicting default server block:

Comment out the default server block in `/etc/nginx/nginx.conf` (around lines 37-46):

```bash
sudo sed -i '37,46s/^/#/' /etc/nginx/nginx.conf
```

### Test and reload Nginx:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## Step 4: Firewall Configuration

### Open required ports:

```bash
sudo firewall-cmd --add-service=http --permanent
sudo firewall-cmd --add-service=https --permanent
sudo firewall-cmd --add-port=8080/tcp --permanent
sudo firewall-cmd --reload
```

### Verify firewall status:

```bash
sudo firewall-cmd --list-all
```

## Step 5: SELinux Configuration (Critical for Fedora)

### Allow Nginx to make network connections:

```bash
sudo setsebool -P httpd_can_network_connect 1
```

**This step is crucial** - without it, you'll get "502 Bad Gateway" errors because SELinux blocks Nginx from connecting to the Streamlit backend.

## Step 6: Testing Local Access

### Test Streamlit directly:

```bash
curl -I http://localhost:8501
```

### Test Nginx proxy:

```bash
curl -I http://localhost:8080
```

### Test via server IP:

```bash
curl -I http://YOUR_SERVER_IP:8080
```

## Step 7: External Access Options

### Option A: Router Port Forwarding

1. Access your router admin panel (usually `http://192.168.1.1` or `http://192.168.0.1`)
2. Find "Port Forwarding" or "Virtual Server" settings
3. Add rule:
   - External Port: 8080
   - Internal IP: YOUR_SERVER_IP
   - Internal Port: 8080
   - Protocol: TCP

### Option B: Using ngrok (Quick solution)

Install ngrok and create public tunnel:

```bash
ngrok http YOUR_SERVER_IP:8080
```

## Step 8: Production Systemd Service (Optional)

### Create systemd service file `/etc/systemd/system/streamlit.service`:

```ini
[Unit]
Description=Streamlit App
After=network.target

[Service]
User=your_username
WorkingDirectory=/path/to/your/project
ExecStart=/path/to/your/project/.venv/bin/streamlit run streamlit_app.py --server.address 0.0.0.0 --server.port 8501
Restart=always

[Install]
WantedBy=multi-user.target
```

### Enable and start service:

```bash
sudo systemctl enable streamlit
sudo systemctl start streamlit
```

## Common Issues and Solutions

### 1. 502 Bad Gateway Error

- **Cause**: SELinux blocking Nginx connections
- **Solution**: Run `sudo setsebool -P httpd_can_network_connect 1`

### 2. Tunnel Connection Failed

- **Cause**: Missing port forwarding or firewall blocking
- **Solution**: Configure router port forwarding and check firewall settings

### 3. Connection Refused

- **Cause**: Streamlit running on localhost only
- **Solution**: Use `--server.address 0.0.0.0` instead of `127.0.0.1`

### 4. Nginx Configuration Conflicts

- **Cause**: Multiple server blocks listening on same port
- **Solution**: Comment out default server block in main nginx.conf

## Security Considerations

### For production deployment:

1. **Use HTTPS**: Set up SSL certificates with Let's Encrypt
2. **Firewall**: Only open necessary ports
3. **Authentication**: Add basic auth or integrate with authentication system
4. **Rate limiting**: Configure Nginx rate limiting
5. **Log monitoring**: Monitor access and error logs

### SSL Setup with Let's Encrypt:

```bash
sudo dnf install certbot python3-certbot-nginx
sudo certbot --nginx
```

## Monitoring and Maintenance

### Check service status:

```bash
sudo systemctl status nginx
sudo systemctl status streamlit
```

### View logs:

```bash
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/access.log
tail -f streamlit.log
```

### Restart services if needed:

```bash
sudo systemctl restart nginx
sudo systemctl restart streamlit
```

## Network Architecture Summary

```
Internet → Router (Port Forward) → Server Firewall → Nginx (Port 8080) → Streamlit (Port 8501)
```

## Virtual Machine Considerations

If deploying in a VM:

1. **UTM/VMware**: Use bridged network mode for direct IP access
2. **VirtualBox**: Configure port forwarding in VM settings
3. **Cloud VMs**: Configure security groups and firewall rules

## Testing Checklist

- [ ] Streamlit accessible on localhost:8501
- [ ] Nginx accessible on localhost:8080
- [ ] Server IP accessible from local network
- [ ] External access working (router/ngrok configured)
- [ ] Firewall ports open
- [ ] SELinux configured correctly
- [ ] Services start on boot
- [ ] Logs show no errors

## Final Notes

- Use port 8080 instead of 80 to avoid ISP port blocking
- Always test locally before configuring external access
- Monitor logs for security and performance issues
- Regular backups of configuration files recommended
