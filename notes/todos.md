- [ ] MessagePack or Protobuf
- [x] Disable WebTransport initial handshake, make it a python feature and need to make it work
- [x] Treesitter language definition > TextMate language
- [x] Form handling
  - [ ] LSP support 
- [x] Path-based routing option over path dict routing
  - [x] PJAX for path-based routing
  - [ ] LSP support
- [ ] SPA prevent changing URL if cannot connect to server
- [ ] Make sure HTTP fallback is LongPolling protocol
- [ ] More lifecycle than on_load
- [x] Call async functions or expressions in handlers (implicit and explicit)
  - [x] Support for binding to the waiting state of async functions or expressions like:
```
<button @click="my_async_func", $bind:busy="is_btn_busy">
```
- [ ] Support multiline expressions in handlers like:
```
<button @click="""
    result = await my_async_func()
    put_in_db(result)
    my_string = format(result)
""">
<p>{my_string}</p>
```
  - see pyhtml / Evaluate Multiline Handlers chat for this
```
textmate may not need to support syntax highlighting inside the """ """ until Tree-sitter loads. I think tree-sitter is ultimately what is used to build the highlight grammar for GitHub code blocks and source view anyway, so tmLanguage only matters for first load.

as long as the """ """ doesn't break the HTML syntax highlighting i dont care if the python code in there is missed in initial paint.

I agree with not auto promoting
```
- [ ] Integrate with FastAPI and Flask
- [ ] Plugin system


