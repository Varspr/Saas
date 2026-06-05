#!/usr/bin/env bash
# Bootstrap свежей Ubuntu GPU-VM под весь стек (api + worker(GPU) + redis + db + frontend).
#
# Предполагается: Ubuntu 22.04, драйвер NVIDIA уже установлен (на Lambda/Vast/
# RunPod-VM так и есть — проверьте `nvidia-smi`), есть sudo, репозиторий склонирован.
#
# Использование на машине:
#   git clone <ваш-репозиторий> saas && cd saas
#   cp .env.gpu.example .env && nano .env   # вписать PUBLIC_API_BASE_URL = публичный IP
#   bash deploy/gpu_vm_bootstrap.sh
set -euo pipefail

echo "==> Проверка GPU"
nvidia-smi || { echo "Нет nvidia-smi: установите драйвер NVIDIA"; exit 1; }

echo "==> Docker"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "$USER" || true
fi

echo "==> nvidia-container-toolkit (доступ к GPU из контейнеров)"
if ! docker info 2>/dev/null | grep -qi nvidia; then
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
    | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
    | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
    | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null
  sudo apt-get update
  sudo apt-get install -y nvidia-container-toolkit
  sudo nvidia-ctk runtime configure --runtime=docker
  sudo systemctl restart docker
fi

echo "==> .env"
[ -f .env ] || cp .env.gpu.example .env
grep -q "CHANGE_ME_PUBLIC_IP" .env && \
  echo "⚠️  Впишите публичный IP в PUBLIC_API_BASE_URL в .env перед доступом с браузера!"

echo "==> Сборка и запуск (первый раз долго: образ ~15 ГБ + веса)"
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build

echo
echo "Готово. Полезное:"
echo "  docker compose logs -f worker      # логи воркера (скачивание весов, обработка)"
echo "  docker compose -f docker-compose.yml -f docker-compose.gpu.yml \\"
echo "      exec worker python /opt/app/scripts/gpu_check.py   # проверка готовности"
echo "  API:   http://<этот-IP>:8000/docs"
echo "  Сайт:  http://<этот-IP>:3000"
