# Yoga Booker (microservices on Kubernetes)

Python FastAPI services + one PostgreSQL database.
One service manages yoga classes (create/list/reserve/release).
The other books participants and calls the class service to reserve seats.
Both expose a very simple web UI (no frameworks, just HTML + fetch).

# Build & push Docker images
```
docker login -u eandmsz
cd
git clone https://github.com/eandmsz/YogaBooking
cd YogaBooking

docker build -t docker.io/eandmsz/class-service:1.0.2 services/class-service
docker push docker.io/eandmsz/class-service:1.0.2
docker build -t docker.io/eandmsz/booking-service:1.0.2 services/booking-service
docker push docker.io/eandmsz/booking-service:1.0.2
```

# Kubernetes deploy (namespace, DB, services, ingress, policies)
Note: 20 & 21 downloads the images we have uploaded above
```
minikube status
minikube start
minikube addons enable ingress
kubectl apply -f YogaBooking/k8s/00-namespace.yaml
kubectl apply -f YogaBooking/k8s/10-postgres.yaml
kubectl apply -f YogaBooking/k8s/20-class-service.yaml
kubectl apply -f YogaBooking/k8s/21-booking-service.yaml
kubectl apply -f YogaBooking/k8s/30-ingress.yaml
kubectl apply -f YogaBooking/k8s/40-networkpolicies.yaml
kubectl get pods -A
```

# Adding IP address of the services to /etc/hosts so the local URLs work
```
echo "$(minikube ip)  classes.yoga.local booking.yoga.local" | sudo tee -a /etc/hosts
```

# Troubleshooting
Check Pod logs:
```
kubectl -n yoga-booker logs -f deploy/booking-service
```
Redeploying services with an updated image (after pushing the updated version to Dockerhub)
```
kubectl -n yoga-booker set image deploy/class-service app=docker.io/eandmsz/class-service:1.0.2
kubectl -n yoga-booker rollout status deploy/class-service
kubectl -n yoga-booker set image deploy/booking-service app=docker.io/eandmsz/booking-service:1.0.2
kubectl -n yoga-booker rollout status deploy/booking-service
kubectl get pods -n yoga-booker
```

Open:
- https://classes.yoga.local/admin (create classes)
- https://booking.yoga.local/ (book seats)

Swagger UIs:
- https://classes.yoga.local/docs
- https://booking.yoga.local/docs

## Scale

kubectl scale deploy class-service -n yoga-booker --replicas=3
kubectl scale deploy booking-service -n yoga-booker --replicas=5


(or enable the provided HorizontalPodAutoscaler objects)

## Smoke tests

# List classes (none yet)
curl -k https://classes.yoga.local/classes

# Create a class (admin token needs to match env in deployment, default "changeme")
curl -k -X POST https://classes.yoga.local/classes \
-H 'Content-Type: application/json' \
-H 'x-admin-token: changeme' \
-d '{"title":"Yin Yoga","instructor":"Maya","start_time":"2025-10-01T18:00:00Z","capacity":12}'


# Book a seat
CLASS_ID=<uuid from create response>
curl -k -X POST https://booking.yoga.local/bookings \
-H 'Content-Type: application/json' \
-d '{"class_id":"'$CLASS_ID'","name":"Alex","email":"alex@example.com"}'


# Check bookings
curl -k 'https://booking.yoga.local/bookings?class_id='$CLASS_ID
