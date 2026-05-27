cd /home/ubuntu/apps/gasolineras_tracker

# 1) Parar procesos anteriores
kill "$(cat gasolineras_tracker.pid)" 2>/dev/null || true
rm -f gasolineras_tracker.pid
rm -f gasolineras_tracker.log

# 2) Lanzar gasolineras_tracker
nohup python -u gasolineras_tracker.py >> gasolineras_tracker.log 2>&1 &
echo $! > create_oci_instance_marseille.pid

# 3) Verificar PIDs
ps -fp "$(cat gasolineras_tracker.pid)"