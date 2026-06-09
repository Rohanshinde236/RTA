import { io } from 'socket.io-client'

const URL = import.meta.env.DEV ? 'http://127.0.0.1:5000' : window.location.origin

export const socket = io(URL, {
  transports: ['websocket', 'polling'],
  reconnectionDelay: 1000,
  reconnectionDelayMax: 5000,
})
