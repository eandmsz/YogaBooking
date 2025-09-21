# Yoga Booker (microservices on Kubernetes)

Python FastAPI services + one PostgreSQL database.
One service manages yoga classes (create/list/reserve/release).
The other books participants and calls the class service to reserve seats.
Both expose a very simple web UI (no frameworks, just HTML + fetch).

# Build & push Docker images
```
cd
git clone https://github.com/eandmsz/YogaBooking
export DOCKER_USER=eandmsz
docker login -u $DOCKER_USER

cd YogaBooking/services/class-service
IMAGE=$DOCKER_USER/yoga-class-service:1.0.0
docker build -t $IMAGE .
docker push $IMAGE

cd
cd YogaBooking/services/booking-service
IMAGE=$DOCKER_USER/yoga-booking-service:1.0.0
docker build -t $IMAGE .
docker push $IMAGE
```

# Generate the base64 strings from the sql files, so we can embed them into our 10-postgres.yaml file directly
```
cd
cd YogaBooking/db
openssl base64 -A -in 01_classes.sql
openssl base64 -A -in 02_bookings.sql
```

# Kubernetes deploy (namespace, DB, services, ingress, policies)
Note: 20 & 21 downloads the images we have uploaded above
```
kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/10-postgres.yaml
kubectl apply -f k8s/20-class-service.yaml
kubectl apply -f k8s/21-booking-service.yaml
kubectl apply -f k8s/30-ingress.yaml
kubectl apply -f k8s/40-networkpolicies.yaml
```

## Access

Add hosts pointing to your Ingress controller IP:

classes.yoga.local -> <LB IP>
booking.yoga.local -> <LB IP>

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
