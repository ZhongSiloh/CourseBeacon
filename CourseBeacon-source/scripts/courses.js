async page => {
  for (const frame of page.frames()) {
    if (await frame.locator('#courseList').count()) {
      return await frame.evaluate(() => ({
        ready: true,
        courses: [...document.querySelectorAll('#courseList > li.course')]
          .filter(li => !li.querySelector('.not-open-tip')?.textContent.includes('课程已结束'))
          .map(li => ({id: li.id, name: li.querySelector('.course-name')?.textContent.trim(),
            url: li.querySelector('h3 a')?.href})).filter(c => c.url),
        ended: [...document.querySelectorAll('#courseList > li.course')]
          .filter(li => li.querySelector('.not-open-tip')?.textContent.includes('课程已结束')).length,
        folders: [...document.querySelectorAll('#fileList > li')].length
      }));
    }
  }
  return {ready:false, login:page.url().includes('passport'), url:page.url()};
}
