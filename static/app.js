(() => {
  const store = { get(k) { try { return localStorage.getItem(k)==='true'; } catch { return false; } }, set(k,v) { try { localStorage.setItem(k,String(v)); } catch {} } };
  for (const [id, cls] of [['contrast','high-contrast'],['font-size','large-text']]) {
    const button=document.getElementById(id); if(!button) continue;
    const apply=(value)=>{document.documentElement.classList.toggle(cls,value);button.setAttribute('aria-pressed',String(value));};
    apply(store.get(id)); button.addEventListener('click',()=>{const active=button.getAttribute('aria-pressed')!=='true';apply(active);store.set(id,active);});
  }
  const menu = document.querySelector('.access-menu');
  const close = () => { menu.open = false; menu.querySelector('summary').focus(); };
  if (menu) {
    menu.querySelector('.access-close').addEventListener('click', close);
    menu.addEventListener('keydown', event => { if (event.key === 'Escape') { event.preventDefault(); close(); } });
    document.addEventListener('click', event => { if (!menu.contains(event.target)) menu.open = false; });
  }
  document.getElementById('reset-accessibility')?.addEventListener('click', () => {
    for (const [id, cls] of [['contrast','high-contrast'],['font-size','large-text']]) {
      document.documentElement.classList.remove(cls);
      document.getElementById(id).setAttribute('aria-pressed', 'false');
      store.set(id, false);
    }
  });
  const errors=document.querySelector('.error-summary'); if(errors) errors.focus();
})();
