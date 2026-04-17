// Inject the interceptor into the page context so it can access
// WebGLRenderingContext and WebGL2RenderingContext on the page's window.
const script = document.createElement('script');
script.src = chrome.runtime.getURL('interceptor.js');
(document.head || document.documentElement).appendChild(script);
