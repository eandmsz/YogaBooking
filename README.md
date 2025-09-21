# Yoga Booker (microservices on Kubernetes)

Python FastAPI services + one PostgreSQL database.
One service manages yoga classes (create/list/reserve/release).
The other books participants and calls the class service to reserve seats.

# Build & push Docker images
```
docker login -u eandmsz
cd
git clone https://github.com/eandmsz/YogaBooking
cd YogaBooking

docker build -t docker.io/eandmsz/booking-service:2.0.0 services/booking-service
docker push docker.io/eandmsz/booking-service:2.0.0
docker build -t docker.io/eandmsz/booking-worker:2.0.0 services/booking-worker
docker push docker.io/eandmsz/booking-worker:2.0.0
docker build -t docker.io/eandmsz/class-service:2.0.0 services/class-service
docker push docker.io/eandmsz/class-service:2.0.0
```

# Kubernetes deploy (namespace, DB, services, ingress, policies)
Note: 20 & 21 downloads the images we have uploaded above
```
minikube status
minikube start
minikube addons enable ingress
```
```
kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/10-postgres.yaml
kubectl apply -f k8s/12-rabbitmq.yaml
kubectl apply -f k8s/20-class-service.yaml
kubectl apply -f k8s/21-booking-service.yaml
kubectl apply -f k8s/22-booking-worker.yaml
kubectl apply -f k8s/30-ingress.yaml
kubectl apply -f k8s/40-networkpolicies.yaml
kubectl apply -f k8s/41-np-rabbitmq-egress.yaml
kubectl -n yoga-booker get pods
```

# Adding IP address of the services to /etc/hosts so the local URLs work
```
echo "$(minikube ip)  classes.yoga.local booking.yoga.local" | sudo tee -a /etc/hosts
```

Open:
- http://classes.yoga.local/admin (create classes)
- http://booking.yoga.local/ (book seats)
- http://booking.yoga.local/bookings?class_id= (check bookings)

Swagger UIs:
- http://classes.yoga.local/docs
- http://booking.yoga.local/docs

# Scale-out
```
kubectl -n yoga-booker get pods
kubectl scale deploy class-service -n yoga-booker --replicas=3
kubectl scale deploy booking-service -n yoga-booker --replicas=5
kubectl -n yoga-booker get pods
```

# Troubleshooting
Check Pod logs:
```
kubectl -n yoga-booker logs -f deploy/booking-service
```
Redeploying services with an updated image (after pushing the updated version to Dockerhub)
```
kubectl -n yoga-booker set image deploy/class-service app=docker.io/eandmsz/class-service:1.0.3
kubectl -n yoga-booker rollout status deploy/class-service
kubectl -n yoga-booker set image deploy/booking-service app=docker.io/eandmsz/booking-service:1.0.3
kubectl -n yoga-booker rollout status deploy/booking-service
kubectl -n yoga-booker get deploy class-service -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
kubectl -n yoga-booker get pods
```
Teardown the whole namespace:
```
kubectl delete namespace yoga-booker
```
