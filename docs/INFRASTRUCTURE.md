# ApexRetail POS Infrastructure

## Domains
- POS Web: https://pos.apexpos.cloud
- API: https://api.apexpos.cloud
- Backoffice: https://backoffice.apexpos.cloud

## Project Paths
- Backend: /root/apexretail-pos/backend
- POS Web: /root/apexretail-pos/pos-web
- Public POS Web: /var/www/apexretail-pos

## Services
- API service: apexpos.service
- Web server: nginx

## Rule
Change one layer at a time:
1. Backend
2. API service
3. Nginx
4. Frontend
5. SSL
