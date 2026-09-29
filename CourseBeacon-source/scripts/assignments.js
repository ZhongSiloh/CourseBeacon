async page => {
  const input = __INPUT__;
  const now = () => Date.now();
  async function workFrame() {
    const deadline = now() + 25000;
    while (now() < deadline) {
      for (const f of page.frames()) {
        if (await f.locator('.task-list #status').count().catch(()=>0)) return f;
      }
      await page.waitForTimeout(250);
    }
    throw new Error('未找到受支持的作业列表；可能登录失效或网页结构已变化');
  }
  if (input.listUrl) {
    await page.goto(input.listUrl, {waitUntil:'domcontentloaded', timeout:30000});
  } else {
    await page.goto(input.course.url, {waitUntil:'domcontentloaded', timeout:30000});
    const gate = await page.locator('body').innerText();
    if (gate.includes('人脸信息采集')) throw new Error('超星要求在手机 APP 完成人脸信息采集，此课程暂时无法读取');
    if (page.url().includes('passport2.chaoxing.com')) throw new Error('登录已失效，请点击刷新作业并在 Chrome 中重新登录');
    await page.getByText('作业', {exact:true}).first().click({timeout:20000});
  }
  let f = await workFrame();
  if (await f.locator('#status').inputValue() !== '1') {
    const radio = f.locator('input[name="group-radio"][data="1"]');
    // Wait for the new document, not the old document's already-fired load event.
    await radio.click();
    await f.waitForFunction(() => document.querySelector('#status')?.value === '1', null, {timeout:25000});
  }
  const listUrl = f.url();
  const items = [], seen = new Set();
  for (let n=0; n<200; n++) {
    await f.locator('.task-list').waitFor();
    const data = await f.evaluate(() => ({
      status:document.querySelector('#status')?.value,
      rows:[...document.querySelectorAll('.bottomList > ul > li')].map(li => ({
        title:li.querySelector('.right-content p')?.textContent.trim() || '',
        status:li.querySelector('p.status')?.textContent.trim() || '',
        timeText:li.querySelector('.time')?.textContent.trim() || '',
        timeActive:!!li.querySelector('.time.notOver'),
        timeIcon:li.querySelector('.time img')?.src || '',
        iconClass:li.querySelector('.tag')?.className || '',
        url:li.getAttribute('data') || li.querySelector('a[href]')?.href || '',
        label:li.querySelector('.label')?.textContent.trim() || ''
      })),
      empty:!!document.querySelector('.null-data'),
      hasList:!!document.querySelector('.bottomList'),
      page:document.querySelector('#page .xl-active')?.textContent || '',
      next:!!document.querySelector('#page .xl-nextPage:not(.xl-disabled)')
    }));
    if (data.status !== '1') throw new Error('未完成筛选未生效');
    if (!data.hasList && !data.empty) throw new Error('作业页未呈现列表或空状态');
    for (const row of data.rows) {
      if (!row.url || !/^https?:\/\//.test(row.url)) throw new Error('作业缺少可直接打开的链接');
      if (!seen.has(row.url)) { seen.add(row.url); items.push({...row, observedAt:now()}); }
    }
    if (!data.next) return {items, listUrl};
    const before = await f.locator('.bottomList').innerHTML();
    await f.locator('#page .xl-nextPage:not(.xl-disabled)').click();
    await f.waitForFunction(before => document.querySelector('.bottomList')?.innerHTML !== before,
      before, {timeout:20000});
  }
  throw new Error('作业分页超过安全上限；本课程结果未标记完整');
}
