# בניית מסך הניהול

`admin/index.html` נבנה מהקבצים כאן:

- `punch.*.part` – אפליקציית הכרטיסייה המקורית.
- `app.js` ו-`extra.css` – החלקים של מסך הניהול: יומן, תזכורות, נוסחים, שעות, התראות, הגדרות.
- `build_admin.py` – מחבר את הכול לקובץ אחד.

הרצה מתיקיית השורש של המאגר:

    python3 tools/admin/build_admin.py admin/index.html

האייקונים של מסך הבית נוצרים עם `python3 tools/admin/make_icons.py admin` (צריך Playwright).
