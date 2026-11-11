(() => {
  'use strict';
  const key = 'saha-playlist-preferences-v1';
  const track = {id:'quiet-bloom', title:'شکوفه آرام · SAHA Quiet Bloom', description:'قطعه بی‌کلام اختصاصی سها · مجوز CC0', src:'/assets/saha-quiet-bloom.mp3'};
  const status = document.getElementById('playlist-status');
  const say = message => { status.textContent = message; };
  let preferences = {liked:[], saved:[]};
  try {
    const data = JSON.parse(localStorage.getItem(key));
    if (data && typeof data === 'object') for (const field of ['liked','saved']) {
      preferences[field] = Array.isArray(data[field]) ? data[field].filter(id => id === track.id) : [];
    }
  } catch (_) { say('ذخیره‌سازی مرورگر در دسترس نیست؛ انتخاب‌هات فعلاً فقط در همین صفحه می‌مونن.'); }
  function persist() {
    try { localStorage.setItem(key, JSON.stringify(preferences)); }
    catch (_) { say('مرورگر اجازه ذخیره نداد؛ انتخابت فعلاً فقط در همین صفحه می‌مونه.'); }
  }
  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function player(src) {
    const audio = document.createElement('audio');
    audio.controls = true; audio.preload = 'none'; audio.src = src;
    audio.addEventListener('play', () => document.querySelectorAll('audio').forEach(other => {if (other !== audio) other.pause();}));
    audio.addEventListener('error', () => say('این فایل قابل پخش نیست؛ یک فایل صوتی سازگار انتخاب کن.'));
    return audio;
  }
  const card = element('article', '', 'song-card');
  card.append(element('h3', track.title), element('p', track.description), player(track.src));
  const actions = element('div', '', 'song-actions');
  const controls = {};
  for (const [field, normal, selected] of [['liked','♡ لایک','♥ لایک شد'],['saved','ذخیره','✓ ذخیره شد']]) {
    const button = element('button', '', 'quiet-button'); button.type = 'button';
    button.addEventListener('click', () => {
      preferences[field] = preferences[field].includes(track.id) ? [] : [track.id];
      persist(); sync();
    });
    controls[field] = {button,normal,selected}; actions.append(button);
  }
  card.append(actions); document.getElementById('song-list').append(card);
  function sync() {
    for (const [field, control] of Object.entries(controls)) {
      const active = preferences[field].includes(track.id);
      control.button.textContent = active ? control.selected : control.normal;
      control.button.setAttribute('aria-pressed', String(active));
    }
    const hide = document.getElementById('saved-only').checked && !preferences.saved.includes(track.id);
    card.hidden = hide; document.getElementById('empty-songs').hidden = !hide;
    if (hide) card.querySelector('audio').pause();
  }
  document.getElementById('saved-only').addEventListener('change', sync); sync();
  const form = document.getElementById('suggestion-form');
  form.addEventListener('submit', event => {
    event.preventDefault();
    const title = document.getElementById('song-name').value.trim();
    const artist = document.getElementById('artist-name').value.trim();
    if (!title) { say('اسم آهنگ رو بنویس ♡'); return; }
    const list = document.getElementById('suggestions');
    if (list.children.length >= 20) {say('برای این امتحان، ۲۰ پیشنهاد کافیه ♡'); return;}
    list.append(element('li', title + (artist ? ' · '+artist : '') + ' — پیشنهاد آزمایشی'));
    form.reset(); say('پیشنهادت فقط در همین صفحه اضافه شد؛ چیزی به سالن ارسال نشد ♡');
  });
  const files = new Map();
  const input = document.getElementById('audio-file');
  input.addEventListener('change', () => {
    const file = input.files[0]; input.value = ''; if (!file) return;
    if (!file.type.startsWith('audio/')) { say('لطفاً یک فایل صوتی انتخاب کن.'); return; }
    if (!file.size || file.size > 25*1024*1024) {say('فایل باید بیشتر از صفر و حداکثر ۲۵ مگابایت باشه.');return;}
    if (files.size >= 5) {say('اول یکی از پنج فایل آزمایشی رو حذف کن.');return;}
    const url = URL.createObjectURL(file);
    const row = element('article', '', 'song-card'); const audio = player(url);
    const remove = element('button','حذف فایل آزمایشی','quiet-button local-remove');remove.type='button';
    remove.addEventListener('click', () => {audio.pause();audio.removeAttribute('src');audio.load();URL.revokeObjectURL(url);files.delete(url);row.remove();});
    row.append(element('h3',file.name),element('p','فقط روی دستگاه تو · ارسال نشده'),audio,remove);
    files.set(url, audio);document.getElementById('local-files').append(row);say('فایل برای پخش محلی آماده شد؛ به سرور ارسال نشد.');
  });
  window.addEventListener('pagehide', () => document.querySelectorAll('audio').forEach(audio => audio.pause()));
})();
