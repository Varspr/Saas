# Реалистичный манекен (MakeHuman / MPFB2)

Цель — тело как витринный манекен: гладкое, бело-серое, анатомически верное,
параметрическое по росту/весу. Делаем это через **MPFB2** (MakeHuman Plugin
For Blender 2) — аддон Blender, который генерирует человека скриптом.

## Почему MPFB2, а не SMPL-X

| | MPFB2 / MakeHuman | SMPL-X |
|--|--|--|
| Лицензия результата | **CC0** (можно в коммерции) | бесплатно только research; для SaaS — **платная** лицензия Meshcapade |
| Веса/модель | открытые, ставятся свободно | проприетарные, нельзя «создать», только лицензировать |
| Внешний вид | реалистичный серый меш | такой же серый меш |
| Параметры | рост, вес, мускулатура, пол, пропорции | shape betas |

Вид у обоих одинаковый (серый манекен) — поэтому платить за SMPL-X ради этого
смысла нет. **Фотореализм/кожа здесь не нужны** — манекен и так матовый белый.

## Как это устроено в коде

```
draping.drape(height, weight)               app/pipeline/draping.py
   └─ Blender (если BODY_ENGINE=mpfb)
        └─ drape_cloth.py --body-engine mpfb --height --weight --gender
             └─ make_body.build_mpfb_body()  app/pipeline/blender_scripts/make_body.py
                  • HumanService.create_human(macro_detail_dict=...)
                  • рост/вес → нормированные макро-параметры MakeHuman (0..1)
                  • белый матовый материал
             └─ cloth simulation одежды на теле → output.glb
```

Рост → высота тела, вес → комплекция (через ИМТ). Маппинг в
`make_body.py::_macro_dict`.

## Включить

В окружении (`.env`):
```
BODY_ENGINE=mpfb
BODY_GENDER=male        # male | female | neutral
DRAPE_BACKEND=blender   # MPFB требует Blender
```
Нужен Blender **с установленным MPFB2**. По умолчанию MPFB в образах
**ВЫКЛЮЧЕН** (`INSTALL_MPFB=false`), чтобы сборка не падала — для старта тело
`parametric`. Включить позже:
```
docker build -f backend/Dockerfile.worker.gpu \
  --build-arg INSTALL_MPFB=true \
  --build-arg MPFB_URL=<ссылка на mpfb-*.zip> ...
```

> ⚠️ Важно: у MPFB2 **нет zip в релизах GitHub** — аддон скачивается с сайта
> сообщества MakeHuman: https://static.makehumancommunity.org/mpfb/ (раздел
> Download/Releases). Возьмите оттуда прямую ссылку на `mpfb-X.Y.Z.zip` и
> передайте её в `MPFB_URL`. Список версий:
> https://github.com/makehumancommunity/mpfb2/releases

## Проверка на реальном Blender

Сгенерировать только тело (без пайплайна):
```bash
blender --background \
  --python backend/app/pipeline/blender_scripts/make_body.py -- \
  --height 185 --weight 90 --gender male --output /tmp/body.glb
```
Открыть `/tmp/body.glb` (например, в https://gltf-viewer.donmccurdy.com) —
должен быть реалистичный манекен нужной комплекции.

## Локально без Docker

Поставь Blender (blender.org) + MPFB2 (через Edit → Preferences → Add-ons →
Install из скачанного zip, включить «MPFB»). Затем `BODY_ENGINE=mpfb`,
`DRAPE_BACKEND=blender`, `BLENDER_BIN=/путь/к/blender`.

## ⚠️ Что НЕ протестировано

Реальный запуск MPFB2 я локально проверить не могу (нет Blender/MPFB на машине).
Точные имена API MPFB2 (`HumanService.create_human`, ключи macrodetail) зависят
от версии аддона — `make_body.py` написан под актуальную и при несовпадении даёт
понятную ошибку. На первом запуске на реальном Blender возможна 1 правка имён
API — сверяйтесь с разделом scripting в докментации MPFB2. Параметрический режим
(`BODY_ENGINE=parametric`) работает всегда и без Blender.
