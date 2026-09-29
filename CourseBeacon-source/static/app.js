'use strict';
const $ = id => document.getElementById(id);
let token='', stopped=false, lastItems='', initialized=false;
function el(tag,cls,text){const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;}
function safeURL(url){try{const u=new URL(url);return ['https:','http:'].includes(u.protocol)&&(u.hostname==='chaoxing.com'||u.hostname.endsWith('.chaoxing.com'));}catch{return false;}}
function renderItems(items){
  const signature=JSON.stringify(items);if(signature===lastItems)return;lastItems=signature;
  const fragment=document.createDocumentFragment();
  for(const item of items){
    if(!safeURL(item.url))continue;
    const li=el('li'), a=el('a','row-link');
    a.href=item.url;a.target='_blank';a.rel='noopener noreferrer';
    a.title=item.course+' · '+item.title;
    a.setAttribute('aria-label',item.course+'：'+item.title+'，'+item.status+'，'+item.timeText);
    const cls=item.iconClass.includes('icon-zy-g')?'icon-zy-g':item.iconClass.includes('icon-zy')?'icon-zy':'tag-fallback';
    const icon=el('div','tag work-icon '+cls,cls==='tag-fallback'?'作业':undefined);icon.setAttribute('aria-hidden','true');
    a.append(icon);
    const right=el('div','right-content');right.append(el('p','overHidden2 fl',item.title));
    if(item.label)right.append(el('span','label',item.label));
    right.append(el('div','clear'),el('p','status fl',item.status));a.append(right);
    if(item.timeText){const t=el('div','time'+(item.timeActive?' notOver':''));
      if(item.timeIcon&&item.timeActive){const img=el('img');img.src='/endTime.png';img.alt='';t.append(img);}
      t.append(document.createTextNode(item.timeText));a.append(t);}
    a.append(el('div','clearfix'));li.append(a);
    if(item.stale)li.append(el('span','stale-note','本课程同步失败，当前为上次结果'));
    fragment.append(li);
  }
  $('items').replaceChildren(fragment);
}
async function action(path,body={}){
  if(!token)token=(await(await fetch('/api/session')).json()).token;
  const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-CourseBeacon-Token':token},body:JSON.stringify(body)});
  const data=await response.json();if(!response.ok)throw Error(data.error||'操作失败');return data;
}
async function poll(){
  if(stopped)return;
  try{
    const r=await fetch('/api/state');if(!r.ok)throw Error('服务不可用');const s=await r.json();
    renderItems(s.items);
    $('notice').className=s.status;$('notice').textContent=s.message;
    $('empty').hidden=!(s.status==='ready'&&!s.items.length);
    $('summary').textContent=(s.updatedAt?'更新于 '+new Date(s.updatedAt).toLocaleTimeString('zh-CN',{hour12:false})+' · ':'')+
      s.items.length+' 项未完成 · 排除 '+s.ended+' 门已结束课程'+(s.items.some(i=>i.stale)?' · 含待核验缓存':'');
    $('refresh').disabled=s.running;$('refresh').textContent=s.running?'同步中 '+s.completed+'/'+s.total:'刷新作业';
    $('sync-note').textContent='剩余时间直接读取超星原文，每轮同步结束后 '+s.interval+' 秒再次检查。';
    $('errors').hidden=!s.errors.length;
    $('errors').querySelector('ul').replaceChildren(...s.errors.map(e=>el('li','',e.course+'：'+e.message)));
    if(!initialized){$('port').value=s.nextPort;initialized=true;}
  }catch(e){$('notice').className='error';$('notice').textContent='无法连接 CourseBeacon，请重新打开程序。';}
  if(!stopped)setTimeout(poll,1500);
}
$('refresh').onclick=async()=>{try{await action('/api/refresh');$('notice').textContent='已安排刷新…';}catch(e){$('notice').textContent=e.message;}};
$('settings-toggle').onclick=()=>{$('settings').hidden=!$('settings').hidden;$('settings-toggle').setAttribute('aria-expanded',String(!$('settings').hidden));};
$('save').onclick=async()=>{try{await action('/api/settings',{port:Number($('port').value)});$('settings-message').textContent='已保存，下次启动生效。';}catch(e){$('settings-message').textContent=e.message;}};
$('stop').onclick=async()=>{try{await action('/api/stop');stopped=true;$('notice').className='';$('notice').textContent='CourseBeacon 已退出，可以关闭此页。';$('refresh').disabled=true;}catch(e){$('settings-message').textContent=e.message;}};
poll();
