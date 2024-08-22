import React, { useEffect, useState } from 'react';
import io from 'socket.io-client';
import Draggable from 'react-draggable';  // Import react-draggable
import './App.css';

const socket = io('http://localhost:5000');

function App() {
  const [notes, setNotes] = useState([]);
  const [newNote, setNewNote] = useState('');

  useEffect(() => {
    socket.on('noteCreated', (note) => {
      setNotes((prevNotes) => [...prevNotes, note]);
    });

    socket.on('noteDeleted', (noteId) => {
      setNotes((prevNotes) => prevNotes.filter((note) => note.id !== noteId));
    });

    return () => {
      socket.off('noteCreated');
      socket.off('noteDeleted');
    };
  }, []);

  const handleCreateNote = () => {
    if (newNote.trim() === '') return;
    const note = {
      id: Date.now(),
      content: newNote,
      position: { x: 0, y: 0 }, // Default position
    };
    socket.emit('createNote', note);
    setNewNote('');
  };

  const handleDeleteNote = (id) => {
    socket.emit('deleteNote', id);
  };

  const handleDrag = (e, data, id) => {
    const updatedNotes = notes.map(note =>
      note.id === id ? { ...note, position: { x: data.x, y: data.y } } : note
    );
    setNotes(updatedNotes);
    // Optionally, emit the updated note position to the server
    // socket.emit('updateNotePosition', { id, position: { x: data.x, y: data.y } });
  };

  return (
    <div className="App">
      <div className="board">
        {notes.map((note) => (
          <Draggable
            key={note.id}
            position={note.position}
            onStop={(e, data) => handleDrag(e, data, note.id)}
          >
            <div className="sticky-note">
              <p>{note.content}</p>
              <button onClick={() => handleDeleteNote(note.id)}>Delete</button>
            </div>
          </Draggable>
        ))}
      </div>
      <div className="controls">
        <input
          type="text"
          placeholder="Write a note..."
          value={newNote}
          onChange={(e) => setNewNote(e.target.value)}
        />
        <button onClick={handleCreateNote}>Create Note</button>
      </div>
    </div>
  );
}

export default App;
